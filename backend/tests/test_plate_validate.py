from backend.modules.anpr.validate import has_known_state_code, is_plausible_plate


def test_accepts_common_indian_plate_formats():
    for plate in ("DL01AB1234", "UP16AB1234", "HR26DK1234", "MH12AB1234"):
        assert is_plausible_plate(plate), plate


def test_rejects_obvious_garbage():
    """The exact failure modes the classical+Tesseract combo was producing."""
    for garbage in ("A", "SW", "123", "ABC", "", "12", "AB"):
        assert not is_plausible_plate(garbage), garbage


def test_rejects_all_letters_or_all_digits():
    assert not is_plausible_plate("ABCDEFGH")
    assert not is_plausible_plate("12345678")


def test_does_not_reject_unusual_but_plausible_formats():
    # short RTO code, short series -- unusual but structurally plausible, must
    # not be hard-rejected by an overly rigid format regex
    assert is_plausible_plate("DL1A1234")


def test_has_known_state_code():
    assert has_known_state_code("DL01AB1234")
    assert has_known_state_code("MH12AB1234")
    assert not has_known_state_code("ZZ01AB1234")
