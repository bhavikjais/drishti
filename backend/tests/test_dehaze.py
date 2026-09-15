import numpy as np

from backend.config import DehazeConfig
from backend.core.dehaze import CLEAR, HAZY, analyze_haze, dehaze_frame, process_frame


def clear_scene(shape=(120, 160)) -> np.ndarray:
    """A high-contrast, multi-color scene with genuine near-black regions -
    every local patch has SOME channel near zero, so its dark channel is
    close to 0 almost everywhere, same as the Dark Channel Prior's
    assumption about real haze-free outdoor images."""
    h, w = shape
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[: h // 2, : w // 2] = (0, 0, 255)   # BGR red
    img[: h // 2, w // 2 :] = (0, 255, 0)   # green
    img[h // 2 :, : w // 2] = (255, 0, 0)   # blue
    img[h // 2 :, w // 2 :] = (0, 0, 0)     # black
    return img


def apply_synthetic_haze(clear: np.ndarray, transmission: float, atmospheric_light=(200, 200, 200)) -> np.ndarray:
    """The physical haze imaging model this whole module inverts:
    I = J*t + A*(1-t). Used here to generate a known-hazy test image from a
    known-clear one, with a known ground-truth transmission to check
    against."""
    clear_f = clear.astype(np.float32)
    a = np.array(atmospheric_light, dtype=np.float32)
    hazy = clear_f * transmission + a * (1.0 - transmission)
    return np.clip(hazy, 0, 255).astype(np.uint8)


def test_clear_scene_is_classified_clear():
    cfg = DehazeConfig()
    clear = clear_scene()
    stats = analyze_haze(clear, cfg)
    assert stats.classification == CLEAR
    assert stats.dark_channel_mean < cfg.haze_dark_channel_threshold


def test_hazy_scene_is_classified_hazy():
    cfg = DehazeConfig()
    hazy = apply_synthetic_haze(clear_scene(), transmission=0.3)
    stats = analyze_haze(hazy, cfg)
    assert stats.classification == HAZY
    assert stats.dark_channel_mean >= cfg.haze_dark_channel_threshold


def test_clear_scene_is_not_touched_by_process_frame():
    cfg = DehazeConfig()
    clear = clear_scene()
    out, info = process_frame(clear, cfg)
    assert info.enhanced is False
    assert info.classification == CLEAR
    assert np.array_equal(out, clear)  # untouched, not even copied/reprocessed


def test_dehazing_increases_contrast_of_a_hazy_scene():
    cfg = DehazeConfig()
    clear = clear_scene()
    hazy = apply_synthetic_haze(clear, transmission=0.3)
    out, info = process_frame(hazy, cfg)

    assert info.enhanced is True
    assert info.classification == HAZY
    assert out.std() > hazy.std()  # haze visibly reduces contrast - dehazing should restore some of it


def test_dehazing_recovers_something_closer_to_the_original_scene():
    cfg = DehazeConfig()
    clear = clear_scene()
    hazy = apply_synthetic_haze(clear, transmission=0.3)
    out, _info = process_frame(hazy, cfg)

    dist_before = float(np.abs(hazy.astype(np.float32) - clear.astype(np.float32)).mean())
    dist_after = float(np.abs(out.astype(np.float32) - clear.astype(np.float32)).mean())
    assert dist_after < dist_before


def test_denser_haze_yields_lower_estimated_transmission():
    cfg = DehazeConfig()
    clear = clear_scene()
    light_haze = apply_synthetic_haze(clear, transmission=0.8)
    dense_haze = apply_synthetic_haze(clear, transmission=0.2)

    _out1, _stats1, t_light = dehaze_frame(light_haze, cfg)
    _out2, _stats2, t_dense = dehaze_frame(dense_haze, cfg)
    assert t_dense < t_light


def test_output_shape_and_dtype_preserved():
    cfg = DehazeConfig()
    hazy = apply_synthetic_haze(clear_scene((80, 100)), transmission=0.3)
    out, _info = process_frame(hazy, cfg)
    assert out.shape == hazy.shape
    assert out.dtype == hazy.dtype


def test_invalid_and_empty_frames_are_handled_safely():
    cfg = DehazeConfig()
    out, info = process_frame(None, cfg)
    assert info.enhanced is False and info.classification == CLEAR
    assert out is None

    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    out, info = process_frame(empty, cfg)
    assert info.enhanced is False
    assert out.size == 0


def test_enabled_false_suppresses_dehazing_but_keeps_classification():
    cfg = DehazeConfig(enabled=False)
    hazy = apply_synthetic_haze(clear_scene(), transmission=0.3)
    out, info = process_frame(hazy, cfg)
    assert info.classification == HAZY  # still correctly classified
    assert info.enhanced is False  # but not dehazed, master switch off
    assert np.array_equal(out, hazy)


def test_configuration_defaults():
    default = DehazeConfig()
    assert default.enabled is True
    assert default.haze_dark_channel_threshold == 0.25
    assert 0.0 < default.omega <= 1.0
