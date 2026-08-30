from backend.modules.anpr.ocr import normalize_plate, plates_match


def test_normalize_strips_spaces_hyphens_and_uppercases():
    assert normalize_plate("dl-01 ab 1234") == "DL01AB1234"
    assert normalize_plate("DL 01 AB 1234") == "DL01AB1234"
    assert normalize_plate("  dl01ab1234  ") == "DL01AB1234"


def test_normalize_drops_non_whitelisted_characters():
    assert normalize_plate("DL01@AB#1234!") == "DL01AB1234"


def test_normalize_empty_input():
    assert normalize_plate("") == ""
    assert normalize_plate(None) == ""


def test_plates_match_exact_after_normalization():
    is_match, sim = plates_match("dl-01 ab 1234", "DL01AB1234", threshold=0.85, max_len_diff=2)
    assert is_match is True
    assert sim == 1.0


def test_plates_match_tolerates_single_character_ocr_confusion():
    # one character misread (4 -> Z) on a 10-char plate: similarity 0.9 >= 0.85
    is_match, sim = plates_match("DL01AB1234", "DL01AB123Z", threshold=0.85, max_len_diff=2)
    assert is_match is True
    assert 0.85 <= sim < 1.0


def test_plates_match_rejects_genuinely_different_plate():
    is_match, sim = plates_match("DL01AB1234", "MH12CD5678", threshold=0.85, max_len_diff=2)
    assert is_match is False
    assert sim < 0.85


def test_plates_match_rejects_large_length_difference_regardless_of_similarity():
    # short candidate could look "similar" by naive metrics but must be rejected
    # outright once the length gap exceeds max_len_diff - no uncontrolled fuzzy
    # matching that could produce a dangerous false positive.
    is_match, sim = plates_match("AB1234", "DL01AB1234", threshold=0.5, max_len_diff=2)
    assert is_match is False
    assert sim == 0.0


def test_plates_match_empty_inputs_never_match():
    assert plates_match("", "DL01AB1234", threshold=0.85, max_len_diff=2) == (False, 0.0)
    assert plates_match("DL01AB1234", "", threshold=0.85, max_len_diff=2) == (False, 0.0)
