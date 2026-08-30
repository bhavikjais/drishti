"""Targeted test for the new PlateOcr backend selection (fast-plate-ocr
primary / Tesseract fallback) -- construction, status reporting, and basic
read() correctness. Real-plate reading accuracy is proven separately by the
end-to-end video test; this confirms the wiring and confidence scale.
"""
import numpy as np
import pytest

from backend.modules.anpr.ocr import PlateOcr


@pytest.fixture(scope="module")
def ocr():
    return PlateOcr()


def test_constructs_and_reports_availability(ocr):
    assert ocr.available in (True, False)
    assert ocr.status.backend in ("fast_plate_ocr", "tesseract")
    assert ocr.status.ocr_ready == ocr.available


def test_status_to_dict_keeps_existing_keys(ocr):
    d = ocr.status.to_dict()
    # existing API/frontend contract keys must still be present
    for key in ("ocr_available", "tesseract_path", "tesseract_version", "reason"):
        assert key in d


def test_read_on_empty_crop_returns_none_none(ocr):
    assert ocr.read(np.zeros((0, 0, 3), dtype=np.uint8)) == (None, None)


def test_read_confidence_is_on_a_0_to_100_scale(ocr):
    if not ocr.available:
        pytest.skip("no OCR backend available in this environment")
    # a blank crop won't read real text, but IF it returns a confidence it
    # must be on the same 0-100 scale AnprConfig.min_read_confidence expects
    _text, confidence = ocr.read(np.full((60, 200, 3), 200, dtype=np.uint8))
    if confidence is not None:
        assert 0.0 <= confidence <= 100.0
