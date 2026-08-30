"""License-plate localization within a vehicle crop.

PlateDetector now tries a real trained plate-detector neural net first
(open-image-models -- ONNX YOLO, from the fast-alpr project) and falls back
to the original classical edge/contour heuristic if that package isn't
installed or fails to construct (missing model download, no network at
first-run time, etc.) -- ANPR degrades gracefully rather than crashing.
The classical heuristic is unchanged from before: real plates are one of the
few high-contrast, rectangular, ~2:1-6:1 aspect-ratio regions on the
back/front of a vehicle, which Canny edges + contour filtering finds
reliably enough to hand off to OCR, just less accurately than a trained
detector on real-world footage (measured: classical localization regularly
boxes bumpers/grilles instead of the actual plate, which is why OCR on top
of it was reading "SARGOSE"/"ZAR6O6L" instead of real plates).
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class PlateCandidate:
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2, relative to the crop passed in
    confidence: float = 0.0


class _ClassicalContourDetector:
    """Zero-dependency fallback -- unchanged from the original heuristic."""

    _TYPICAL_ASPECT = 3.4
    _MIN_ASPECT = 2.0
    _MAX_ASPECT = 6.0
    _MIN_AREA_RATIO = 0.008
    _MAX_AREA_RATIO = 0.5
    # Downscale large vehicle crops before edge detection - plate shape
    # doesn't need full resolution to locate, and Canny/bilateralFilter cost
    # scales with pixel count.
    _MAX_WORKING_DIM = 800

    def locate(self, vehicle_crop: np.ndarray) -> PlateCandidate | None:
        if vehicle_crop is None or vehicle_crop.size == 0:
            return None
        h0, w0 = vehicle_crop.shape[:2]
        if h0 < 10 or w0 < 10:
            return None

        scale = min(1.0, self._MAX_WORKING_DIM / max(h0, w0))
        small = (
            cv2.resize(vehicle_crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            if scale < 1.0 else vehicle_crop
        )

        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 11, 17, 17)
        edges = cv2.Canny(gray, 30, 200)
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:20]

        h, w = gray.shape[:2]
        frame_area = h * w
        best_box, best_score = None, None
        for contour in contours:
            x, y, cw, ch = cv2.boundingRect(contour)
            if ch == 0 or cw == 0:
                continue
            aspect = cw / ch
            area_ratio = (cw * ch) / frame_area
            if not (self._MIN_ASPECT <= aspect <= self._MAX_ASPECT):
                continue
            if not (self._MIN_AREA_RATIO <= area_ratio <= self._MAX_AREA_RATIO):
                continue
            score = abs(aspect - self._TYPICAL_ASPECT)
            if best_score is None or score < best_score:
                best_score = score
                best_box = (x, y, x + cw, y + ch)

        if best_box is None:
            return None

        x1, y1, x2, y2 = best_box
        if scale < 1.0:
            inv = 1.0 / scale
            x1, y1, x2, y2 = (int(round(v * inv)) for v in (x1, y1, x2, y2))
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w0, x2), min(h0, y2)
        if x2 <= x1 or y2 <= y1:
            return None
        return PlateCandidate(bbox=(x1, y1, x2, y2), confidence=0.0)


class _NeuralPlateDetector:
    """Wraps open-image-models' pretrained ONNX YOLO plate detector."""

    def __init__(self, model: str = "yolo-v9-t-256-license-plate-end2end", conf_thresh: float = 0.25) -> None:
        from open_image_models import create_detector

        # onnxruntime on Windows auto-registers AzureExecutionProvider
        # alongside CPU; each inference call then tries it first, which is
        # both a hidden network dependency (ANPR must stay offline) and,
        # empirically, ~8-10x slower per call -- pin to CPU explicitly.
        self._detector = create_detector(model, conf_thresh=conf_thresh, providers=["CPUExecutionProvider"])

    def locate(self, vehicle_crop: np.ndarray) -> PlateCandidate | None:
        if vehicle_crop is None or vehicle_crop.size == 0 or 0 in vehicle_crop.shape[:2]:
            # open-image-models' internal letterbox preprocessing divides by
            # the crop's height/width with no guard -- a degenerate (0-size)
            # crop raises ZeroDivisionError instead of just finding nothing.
            return None
        results = self._detector.predict(vehicle_crop)
        if not results:
            return None
        best = max(results, key=lambda r: r.confidence)
        b = best.bounding_box
        x1, y1 = max(0, b.x1), max(0, b.y1)
        x2, y2 = min(vehicle_crop.shape[1], b.x2), min(vehicle_crop.shape[0], b.y2)
        if x2 <= x1 or y2 <= y1:
            return None
        return PlateCandidate(bbox=(x1, y1, x2, y2), confidence=best.confidence)


class PlateDetector:
    """Public interface unchanged -- .locate(crop) -> PlateCandidate | None.
    Tries the neural detector once at construction; if that fails for any
    reason, permanently uses the classical fallback for the lifetime of this
    instance (never retries per-call, which would pay the failed-construction
    cost repeatedly)."""

    def __init__(self) -> None:
        self._impl = self._build_neural()
        self.backend = "neural" if self._impl is not None else "classical"
        if self._impl is None:
            self._impl = _ClassicalContourDetector()

    @staticmethod
    def _build_neural():
        try:
            return _NeuralPlateDetector()
        except Exception:
            return None

    def locate(self, vehicle_crop: np.ndarray) -> PlateCandidate | None:
        return self._impl.locate(vehicle_crop)
