"""Lenient plausibility check for Indian registration numbers.

NOT a strict format validator -- one rigid regex would reject legitimate
unusual plates (Bharat-series 21BH1234AB numeric prefixes, uncommon RTO
codes, 0-3 letter series). Instead this rejects the concrete failure modes
seen in practice ("A", "SW", "123", "ABC" -- the garbage the classical
detector + Tesseract combo was producing) by checking properties every real
Indian plate format shares: a mix of letters and digits, a plausible length,
and a trailing run of digits (the unique-number group every format ends
with).
"""

from __future__ import annotations

import re

from backend.modules.anpr.normalize import INDIAN_STATE_CODES

_TRAILING_DIGITS = re.compile(r"[0-9]{3,4}$")
_MIN_PLAUSIBLE_LENGTH = 6  # shortest realistic normalized plate (short RTO code + short series)
_MAX_PLAUSIBLE_LENGTH = 11


def is_plausible_plate(normalized_text: str) -> bool:
    """True if normalized_text could realistically be a vehicle registration
    number. Used to filter obvious OCR noise out of aggregation -- not to
    validate a specific state's exact format."""
    if not normalized_text:
        return False
    if not (_MIN_PLAUSIBLE_LENGTH <= len(normalized_text) <= _MAX_PLAUSIBLE_LENGTH):
        return False
    has_letter = any(ch.isalpha() for ch in normalized_text)
    has_digit = any(ch.isdigit() for ch in normalized_text)
    if not (has_letter and has_digit):
        return False
    if not _TRAILING_DIGITS.search(normalized_text):
        return False
    return True


def has_known_state_code(normalized_text: str) -> bool:
    """Extra confidence signal (not a hard requirement) -- most plates will
    match, Bharat-series and a few edge cases won't."""
    return normalized_text[:2] in INDIAN_STATE_CODES
