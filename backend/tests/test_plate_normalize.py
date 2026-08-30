from backend.modules.anpr.normalize import clean_plate_text, strip_watermark_noise, trim_to_state_code
from backend.modules.anpr.ocr import normalize_plate


def test_trim_to_state_code_drops_leading_junk():
    assert trim_to_state_code("XDL8CAF1234") == "DL8CAF1234"
    assert trim_to_state_code("ZZDL8CAF1234") == "DL8CAF1234"


def test_trim_to_state_code_falls_back_when_no_state_code_found():
    # never discards -- returns the original if no real state code appears anywhere
    assert trim_to_state_code("ZZZZ1234") == "ZZZZ1234"


def test_strip_watermark_noise_removes_india_and_bharat_tokens():
    assert "INDIA" not in strip_watermark_noise("INDIA DL8CAF1234")
    assert "BHARAT" not in strip_watermark_noise("BHARAT DL8CAF1234")


def test_strip_watermark_noise_does_not_eat_short_substrings():
    # must not strip plain "IN"/"IND" -- too short, would eat real plate chars
    assert "IN" in strip_watermark_noise("MHIN1234")


def test_clean_plate_text_full_pipeline():
    assert clean_plate_text("INDIA DL-01 AB 1234", normalize_plate) == "DL01AB1234"
    assert clean_plate_text("  mh12ab1234  ", normalize_plate) == "MH12AB1234"


def test_clean_plate_text_handles_empty_input():
    assert clean_plate_text("", normalize_plate) == ""
    assert clean_plate_text(None, normalize_plate) == ""


def test_clean_plate_text_does_not_mangle_plate_without_state_code_prefix():
    # e.g. a Bharat-series-style numeric prefix -- no real state code anywhere,
    # so the trim must be a no-op rather than eating the whole string
    assert clean_plate_text("21BH1234AB", normalize_plate) == "21BH1234AB"
