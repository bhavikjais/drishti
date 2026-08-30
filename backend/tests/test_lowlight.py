import math

import numpy as np
import pytest

from backend.config import LowLightConfig
from backend.core.lowlight import (
    LOW_LIGHT, NORMAL, analyze_brightness, compute_adaptive_gamma, enhance_fast, process_frame,
)


def solid_image(value: int, shape=(120, 160, 3)) -> np.ndarray:
    return np.full(shape, value, dtype=np.uint8)


def colored_image(bgr: tuple[int, int, int], shape=(120, 160)) -> np.ndarray:
    img = np.zeros((*shape, 3), dtype=np.uint8)
    img[:, :] = bgr
    return img


def test_bright_frame_is_not_enhanced():
    cfg = LowLightConfig()
    bright = solid_image(200)
    stats = analyze_brightness(bright, cfg)
    assert stats.classification == NORMAL

    out, info = process_frame(bright, cfg)
    assert info.enhanced is False
    assert info.classification == NORMAL
    assert np.array_equal(out, bright)  # untouched, not even copied/reprocessed


def test_dark_frame_triggers_enhancement():
    cfg = LowLightConfig()
    dark = solid_image(20)
    stats = analyze_brightness(dark, cfg)
    assert stats.classification == LOW_LIGHT

    out, info = process_frame(dark, cfg)
    assert info.enhanced is True
    assert info.backend_used == "fast"
    assert info.mean_l_after > info.mean_l_before  # genuinely brighter, not just relabeled


def test_borderline_brightness_threshold_flips_classification():
    base_cfg = LowLightConfig()
    dark = solid_image(60)
    bright = solid_image(180)
    mean_l_dark = analyze_brightness(dark, base_cfg).mean_l
    mean_l_bright = analyze_brightness(bright, base_cfg).mean_l
    assert mean_l_dark < mean_l_bright

    midpoint_cfg = LowLightConfig(mean_threshold=(mean_l_dark + mean_l_bright) / 2, shadow_p10_threshold=0.0)
    assert analyze_brightness(dark, midpoint_cfg).classification == LOW_LIGHT
    assert analyze_brightness(bright, midpoint_cfg).classification == NORMAL


def test_gamma_calculation_matches_formula():
    gamma = compute_adaptive_gamma(mean_l=50.0, target_mean=130.0, gamma_min=0.1)
    expected = math.log(130.0 / 255.0) / math.log(50.0 / 255.0)
    assert abs(gamma - expected) < 1e-9
    assert 0.1 < gamma < 1.0  # brightening, not darkening


def test_gamma_is_noop_when_already_bright_enough():
    assert compute_adaptive_gamma(mean_l=150.0, target_mean=130.0, gamma_min=0.4) == 1.0


def test_gamma_clamped_to_minimum():
    # an extremely dark mean would solve to a gamma far below gamma_min - must clamp, not extrapolate
    gamma = compute_adaptive_gamma(mean_l=1.0, target_mean=130.0, gamma_min=0.4)
    assert gamma == 0.4


def test_clahe_enhancement_brightens_and_preserves_hue_and_shape():
    cfg = LowLightConfig()
    dim_blue = colored_image((90, 20, 15), shape=(100, 140))  # dim, blue-dominant (BGR)
    enhanced = enhance_fast(dim_blue, cfg)

    assert enhanced.shape == dim_blue.shape
    assert enhanced.dtype == dim_blue.dtype
    assert enhanced.mean() > dim_blue.mean()  # actually brighter

    hsv_before = cv2_hue_mean(dim_blue)
    hsv_after = cv2_hue_mean(enhanced)
    assert abs(hsv_before - hsv_after) < 15  # hue roughly preserved - no severe color distortion


def cv2_hue_mean(image: np.ndarray) -> float:
    import cv2
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    return float(hsv[:, :, 0].mean())


def test_invalid_and_empty_frames_are_handled_safely():
    cfg = LowLightConfig()
    out, info = process_frame(None, cfg)
    assert info.enhanced is False and info.classification == NORMAL
    assert out is None

    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    out, info = process_frame(empty, cfg)
    assert info.enhanced is False
    assert out.size == 0


def test_configuration_defaults_and_overrides():
    default = LowLightConfig()
    assert default.backend == "fast"
    assert default.enabled is True
    assert default.mean_threshold == 65.0

    custom = LowLightConfig(mean_threshold=100.0, backend="zero_dce")
    assert custom.mean_threshold == 100.0
    assert custom.backend == "zero_dce"


def test_enhancement_disabled_flag_suppresses_enhancement_but_keeps_classification():
    cfg = LowLightConfig(enabled=False)
    dark = solid_image(20)
    out, info = process_frame(dark, cfg)
    assert info.classification == LOW_LIGHT  # still correctly classified
    assert info.enhanced is False  # but not enhanced, master switch off
    assert np.array_equal(out, dark)


def test_zero_dce_backend_falls_back_gracefully_not_crashes():
    cfg = LowLightConfig(backend="zero_dce")
    dark = solid_image(20)
    out, info = process_frame(dark, cfg)
    assert info.enhanced is True
    assert info.backend_used == "fast"  # graceful fallback, not a crash
    assert info.fallback_reason is not None


def test_output_dimensions_preserved_across_shapes():
    cfg = LowLightConfig()
    for shape in [(64, 64, 3), (100, 200, 3), (37, 91, 3)]:
        dark = solid_image(15, shape=shape)
        enhanced = enhance_fast(dark, cfg)
        assert enhanced.shape == shape


def test_unknown_backend_raises_clear_error():
    cfg = LowLightConfig(backend="not_a_real_backend")
    dark = solid_image(20)
    with pytest.raises(ValueError):
        process_frame(dark, cfg)
