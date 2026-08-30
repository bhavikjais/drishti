"""Integration test: runs the real LowLightPipeline (real video I/O, real
OutputVideoWriter) on a synthetic clip that's half bright / half dark, and
verifies it enhances only the dark half - not "blindly enhancing every
frame" - while preserving the complete output duration/fps.
"""
import cv2
import numpy as np

from backend.config import LowLightConfig
from backend.modules.lowlight.pipeline import LowLightPipeline


def _make_mixed_brightness_video(path, n_bright=8, n_dark=8, fps=10.0, size=(160, 120)):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, size)
    bright = np.full((size[1], size[0], 3), 200, dtype=np.uint8)
    dark = np.full((size[1], size[0], 3), 15, dtype=np.uint8)
    for _ in range(n_bright):
        writer.write(bright)
    for _ in range(n_dark):
        writer.write(dark)
    writer.release()


def test_only_dark_frames_are_enhanced(tmp_path):
    video_path = tmp_path / "mixed.mp4"
    _make_mixed_brightness_video(video_path, n_bright=8, n_dark=8, fps=10.0, size=(160, 120))
    output_path = tmp_path / "out.mp4"

    progress_values = []
    result = LowLightPipeline().run(video_path, output_path, progress_cb=progress_values.append)

    assert result.total_frames == 16
    assert result.low_light_frames == 8
    assert result.enhanced_frames == 8
    assert result.enhanced_percentage == 50.0
    assert result.low_light_detected is True
    assert result.enhancement_applied is True
    assert result.fallback_used is False
    assert progress_values[-1] == 1.0

    cap = cv2.VideoCapture(str(output_path))
    assert cap.isOpened()
    assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 16
    assert abs(cap.get(cv2.CAP_PROP_FPS) - 10.0) < 0.5

    cap.set(cv2.CAP_PROP_POS_FRAMES, 2)  # a bright frame
    ok, bright_out = cap.read()
    assert ok and abs(float(bright_out.mean()) - 200.0) < 2.0  # untouched

    cap.set(cv2.CAP_PROP_POS_FRAMES, 12)  # a dark (enhanced) frame
    ok, dark_out = cap.read()
    assert ok and float(dark_out.mean()) > 15.0  # genuinely brightened, not left dark
    cap.release()


def test_all_bright_video_enhances_nothing(tmp_path):
    video_path = tmp_path / "bright.mp4"
    _make_mixed_brightness_video(video_path, n_bright=10, n_dark=0, fps=10.0, size=(128, 96))
    output_path = tmp_path / "out2.mp4"

    result = LowLightPipeline().run(video_path, output_path)
    assert result.low_light_frames == 0
    assert result.enhanced_frames == 0
    assert result.enhanced_percentage == 0.0
    assert result.low_light_detected is False
    assert result.enhancement_applied is False


def test_disabled_config_never_enhances_even_dark_video(tmp_path):
    video_path = tmp_path / "dark.mp4"
    _make_mixed_brightness_video(video_path, n_bright=0, n_dark=10, fps=10.0, size=(128, 96))
    output_path = tmp_path / "out3.mp4"

    result = LowLightPipeline(config=LowLightConfig(enabled=False)).run(video_path, output_path)
    assert result.low_light_frames == 10  # still correctly classified
    assert result.enhanced_frames == 0  # but never enhanced
    assert result.enhancement_applied is False
