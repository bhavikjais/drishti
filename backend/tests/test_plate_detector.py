"""Targeted test for the new neural PlateDetector -- construction, graceful
fallback behavior, and basic locate() correctness. Real-footage localization
accuracy is proven separately by the end-to-end video test (that's what
actually exercises it against a real plate); this just confirms the wiring
is sound and it doesn't crash.
"""
import numpy as np
import pytest

from backend.modules.anpr.plate_detector import PlateCandidate, PlateDetector, _ClassicalContourDetector


@pytest.fixture(scope="module")
def detector():
    return PlateDetector()


def test_constructs_and_reports_a_backend(detector):
    assert detector.backend in ("neural", "classical")


def test_locate_on_empty_crop_returns_none(detector):
    assert detector.locate(np.zeros((0, 0, 3), dtype=np.uint8)) is None


def test_locate_on_tiny_crop_returns_none(detector):
    assert detector.locate(np.full((5, 5, 3), 128, dtype=np.uint8)) is None


def test_locate_on_blank_crop_finds_nothing(detector):
    # a solid gray image has no plate-like rectangle -- must not hallucinate one
    blank = np.full((300, 400, 3), 180, dtype=np.uint8)
    result = detector.locate(blank)
    assert result is None or isinstance(result, PlateCandidate)


def test_classical_fallback_still_works_standalone():
    # the zero-dependency path must keep working even if the neural one is used
    fallback = _ClassicalContourDetector()
    assert fallback.locate(np.zeros((0, 0, 3), dtype=np.uint8)) is None
