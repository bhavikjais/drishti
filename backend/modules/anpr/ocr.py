"""Plate text OCR: fast-plate-ocr (plate-specialized ONNX model) as the
primary backend, pytesseract (system Tesseract binary) as the fallback, plus
plate-string normalization and search matching.

fast-plate-ocr replaces Tesseract as primary because Tesseract is a
general-purpose text OCR, not trained on plates -- measured on real footage,
it was reading "SARGOSE"/"ZAR6O6L"/single characters off real plate crops
(best similarity against a known real plate: 0.167, nowhere near a usable
threshold). The same video with fast-plate-ocr produces consistent,
near-matching reads (similarity 0.857+). Both are ONNX/pytesseract -- no
cloud OCR, everything stays offline after the one-time model download.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from backend.modules.anpr.normalize import clean_plate_text

try:
    import pytesseract
    _PYTESSERACT_IMPORTED = True
except ImportError:
    _PYTESSERACT_IMPORTED = False

_WINDOWS_CANDIDATE_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]

PLATE_CHAR_WHITELIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_STRIP_CHARS = {" ", "-", ".", "\n", "\t", "_"}


def normalize_plate(text: str) -> str:
    """Uppercase, drop spaces/hyphens/punctuation, keep only whitelisted
    plate characters. Used for BOTH OCR output and user search input so
    'DL-01 AB 1234' and 'dl01ab1234' compare identically. Unchanged from
    before -- normalize.clean_plate_text (the India-aware state-code-trim
    cleanup) is applied separately, only to raw OCR reads inside PlateOcr,
    not here, so existing search-matching behavior/tests are untouched.
    """
    if not text:
        return ""
    text = text.upper()
    for ch in _STRIP_CHARS:
        text = text.replace(ch, "")
    return "".join(ch for ch in text if ch in PLATE_CHAR_WHITELIST)


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def plates_match(candidate_text: str, searched_text: str, threshold: float, max_len_diff: int) -> tuple[bool, float]:
    """Compares an OCR-read plate against a user-searched plate. Both inputs
    are normalized first, so this only ever measures genuine character-level
    OCR noise - never formatting/spacing/case. Conservative by design: a
    length gap beyond max_len_diff is rejected outright regardless of
    similarity, so a short plate can't fuzzy-match a much longer one.
    Returns (is_match, similarity in [0, 1]).
    """
    a, b = normalize_plate(candidate_text), normalize_plate(searched_text)
    if not a or not b:
        return False, 0.0
    if abs(len(a) - len(b)) > max_len_diff:
        return False, 0.0
    distance = _levenshtein(a, b)
    similarity = 1.0 - (distance / max(len(a), len(b)))
    similarity = round(max(0.0, similarity), 3)
    return similarity >= threshold, similarity


@dataclass
class OcrStatus:
    ocr_ready: bool
    backend: str = "tesseract"  # "fast_plate_ocr" | "tesseract"
    tesseract_path: str | None = None
    tesseract_version: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "ocr_available": self.ocr_ready,
            "backend": self.backend,
            "tesseract_path": self.tesseract_path,
            "tesseract_version": self.tesseract_version,
            "reason": self.reason,
        }


def _locate_tesseract() -> str | None:
    on_path = shutil.which("tesseract")
    if on_path:
        return on_path
    for candidate in _WINDOWS_CANDIDATE_PATHS:
        if Path(candidate).is_file():
            return candidate
    return None


def configure_tesseract() -> OcrStatus:
    if not _PYTESSERACT_IMPORTED:
        return OcrStatus(False, reason="pytesseract package not installed")

    exe_path = _locate_tesseract()
    if exe_path is None:
        return OcrStatus(False, reason="tesseract.exe not found on PATH or standard install locations")

    pytesseract.pytesseract.tesseract_cmd = exe_path
    try:
        version = str(pytesseract.get_tesseract_version())
    except Exception as exc:
        return OcrStatus(False, tesseract_path=exe_path, reason=f"tesseract found but failed to run: {exc}")

    try:
        langs = pytesseract.get_languages(config="")
        if "eng" not in langs:
            return OcrStatus(
                False, tesseract_path=exe_path, tesseract_version=version,
                reason=f"eng.traineddata not installed (have: {', '.join(langs) or 'none'})",
            )
    except Exception:
        pass  # can't enumerate languages on some installs; fall through and try a real read

    return OcrStatus(True, tesseract_path=exe_path, tesseract_version=version)


class _TesseractBackend:
    """Fallback OCR -- same preprocessing (aggressive grayscale+CLAHE+Otsu
    threshold) the original implementation used, since Tesseract needs the
    extra help fast-plate-ocr's trained model doesn't."""

    def __init__(self) -> None:
        self.status = configure_tesseract()

    @property
    def available(self) -> bool:
        return self.status.ocr_ready

    def _preprocess(self, plate_crop: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
        target_height = 120  # Tesseract wants roughly 30+ px character height
        scale = max(1.0, target_height / max(1, gray.shape[0]))
        if scale > 1.0:
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        gray = cv2.bilateralFilter(gray, 7, 50, 50)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if np.mean(thresh) < 127:  # plates are dark-text-on-light; flip if inverted
            thresh = cv2.bitwise_not(thresh)
        return thresh

    def read(self, plate_crop: np.ndarray) -> tuple[str | None, float | None]:
        """Returns (normalized_text, confidence 0-100) or (None, None)."""
        if not self.available or plate_crop is None or plate_crop.size == 0:
            return None, None
        processed = self._preprocess(plate_crop)

        best_text, best_conf = None, -1.0
        _CONFIDENT_ENOUGH = 80.0
        for psm in (7, 8):  # 7 = single line, 8 = single word
            config = f"--oem 1 --psm {psm} -c tessedit_char_whitelist={PLATE_CHAR_WHITELIST}"
            try:
                data = pytesseract.image_to_data(processed, config=config, output_type=pytesseract.Output.DICT)
            except Exception:
                continue
            words = [w for w in data.get("text", []) if w and w.strip()]
            confs = [float(c) for c, w in zip(data.get("conf", []), data.get("text", [])) if w and w.strip() and float(c) >= 0]
            if not words:
                continue
            candidate = clean_plate_text("".join(words), normalize_plate)
            confidence = (sum(confs) / len(confs)) if confs else 0.0
            if candidate and confidence > best_conf:
                best_text, best_conf = candidate, confidence
            if best_conf >= _CONFIDENT_ENOUGH:
                break

        if not best_text:
            return None, None
        return best_text, round(best_conf, 1)


class _FastPlateOcrBackend:
    """Primary OCR -- a small ONNX model (CCT architecture) trained
    specifically on plate text. Does its own internal resize/normalize, so
    preprocessing here stays minimal -- heavy binarization would fight the
    model's own trained expectations rather than help it."""

    def __init__(self, model: str = "cct-s-v2-global-model") -> None:
        from fast_plate_ocr import LicensePlateRecognizer

        # Pin to CPU -- see plate_detector.py's _NeuralPlateDetector for why
        # (AzureExecutionProvider is a hidden network dependency + ~8-10x slower).
        self._recognizer = LicensePlateRecognizer(model, providers=["CPUExecutionProvider"])
        self.status = OcrStatus(True, backend="fast_plate_ocr")

    @property
    def available(self) -> bool:
        return True

    def read(self, plate_crop: np.ndarray) -> tuple[str | None, float | None]:
        """Returns (normalized_text, confidence 0-100) or (None, None)."""
        if plate_crop is None or plate_crop.size == 0:
            return None, None
        h = plate_crop.shape[0]
        if h < 16:  # tiny crop upscaled -- the model needs some real pixel detail
            scale = 32 / max(1, h)
            plate_crop = cv2.resize(plate_crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        results = self._recognizer.run(plate_crop, return_confidence=True)
        if not results:
            return None, None
        prediction = results[0]
        text = clean_plate_text(prediction.plate, normalize_plate)
        confidence = float(np.mean(prediction.char_probs)) * 100.0 if prediction.has_confidence else 50.0
        if not text:
            return None, None
        return text, round(confidence, 1)


class PlateOcr:
    """Public interface unchanged -- .available, .status, .read(crop) ->
    (text, confidence 0-100). Tries fast-plate-ocr once at construction; if
    that fails for any reason (package missing, model download failed, no
    network at first-run), permanently falls back to Tesseract for the
    lifetime of this instance."""

    def __init__(self) -> None:
        self._impl = self._build_fast_plate_ocr()
        if self._impl is None:
            self._impl = _TesseractBackend()
        self.status = self._impl.status

    @staticmethod
    def _build_fast_plate_ocr():
        try:
            return _FastPlateOcrBackend()
        except Exception:
            return None

    @property
    def available(self) -> bool:
        return self._impl.available

    def read(self, plate_crop: np.ndarray) -> tuple[str | None, float | None]:
        return self._impl.read(plate_crop)
