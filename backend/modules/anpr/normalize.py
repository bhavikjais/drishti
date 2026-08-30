"""India-aware plate-text cleanup, layered on top of ocr.py's basic
normalize_plate() (uppercase + strip formatting).

The state-code-trim heuristic is adapted from the reference project
(RonLek/ALPR-and-Identification-for-Indian-Vehicles, ocr.py `resultplate()`):
Indian plates always start with a real 2-letter state code, and OCR output is
often preceded by junk (a partial "INDIA" watermark, a smudge misread as a
character) -- trimming from the left until a real state code appears cleans
that up. Unlike the reference project, a failed trim falls back to the
untrimmed text rather than discarding the read entirely.
"""

from __future__ import annotations

INDIAN_STATE_CODES = {
    "AP", "AR", "AS", "BR", "CG", "GA", "GJ", "HR", "HP", "JH", "KA", "KL",
    "MP", "MH", "MN", "ML", "MZ", "NL", "OD", "PB", "RJ", "SK", "TN", "TS",
    "TR", "UP", "UK", "WB", "AN", "CH", "DD", "DL", "JK", "LA", "LD", "PY",
}

_WATERMARK_NOISE = ("INDIA", "BHARAT")


def strip_watermark_noise(text: str) -> str:
    """Drops common plate-sticker watermark text ('INDIA', 'BHARAT') that OCR
    sometimes picks up alongside the actual registration number. Deliberately
    does NOT strip plain 'IN'/'IND' substrings -- those are too short and
    would eat real plate characters (e.g. a plate ending in ...IN12)."""
    upper = text.upper()
    for token in _WATERMARK_NOISE:
        upper = upper.replace(token, "")
    return upper


def trim_to_state_code(normalized_text: str) -> str:
    """Trims leading characters until the first two match a real Indian state
    code, exactly as the reference project's resultplate() does. Returns the
    input UNCHANGED if no state code is ever found (never discards a read)."""
    text = normalized_text
    while len(text) >= 2 and text[:2] not in INDIAN_STATE_CODES:
        text = text[1:]
    return text if len(text) >= 2 else normalized_text


def clean_plate_text(raw: str, normalize_fn) -> str:
    """Full India-aware cleanup pass: strip watermark tokens, run the
    project's existing normalize_fn (ocr.normalize_plate -- uppercase +
    whitelist), then trim to the state code if one is present. Takes
    normalize_fn as a parameter rather than importing it, to avoid a circular
    import between normalize.py and ocr.py."""
    if not raw:
        return ""
    text = strip_watermark_noise(raw)
    text = normalize_fn(text)
    if not text:
        return text
    return trim_to_state_code(text)
