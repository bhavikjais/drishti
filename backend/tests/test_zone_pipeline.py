"""Integration-lite test: runs the real ZonePipeline (real YOLO tracker, real
video I/O) end-to-end on a tiny synthetic clip to prove the zone outline is
actually drawn into the output video - not just that the state machine logic
is correct in isolation (that's covered by test_zone_state.py).
"""
import cv2
import numpy as np

from backend.core.output import YELLOW
from backend.modules.zone.geometry import Zone
from backend.modules.zone.pipeline import ZonePipeline


def _make_synthetic_video(path, n_frames=10, fps=10.0, size=(160, 120)):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, size)
    rng = np.random.default_rng(0)
    for _ in range(n_frames):
        frame = rng.integers(0, 255, (size[1], size[0], 3), dtype=np.uint8)
        writer.write(frame)
    writer.release()


def test_zone_outline_is_drawn_into_every_output_frame(tmp_path):
    video_path = tmp_path / "synthetic.mp4"
    _make_synthetic_video(video_path, n_frames=10, fps=10.0, size=(160, 120))

    zone = Zone(zone_id="z1", video_id="v1", label="Test Zone", shape="rectangle", points=[(0.2, 0.2), (0.6, 0.6)])
    output_path = tmp_path / "out.mp4"

    progress_values = []
    result = ZonePipeline().run(video_path, zone, output_path, progress_cb=progress_values.append)

    assert result.output_video_path == output_path
    assert result.video_info.frame_count == 10
    assert progress_values[-1] == 1.0  # progress callback reaches completion

    cap = cv2.VideoCapture(str(output_path))
    assert cap.isOpened()
    assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 10
    cap.set(cv2.CAP_PROP_POS_FRAMES, 5)
    ok, frame = cap.read()
    cap.release()
    assert ok

    # bottom edge of the rectangle: x in [32,96], y=72 (160x120 frame, zone [0.2,0.6])
    strip = frame[70:74, 40:90]
    matches_yellow = np.all(np.abs(strip.astype(int) - np.array(YELLOW)) < 40, axis=-1)
    assert matches_yellow.any(), "zone outline (YELLOW) not found in output frame at expected boundary"


def test_output_video_full_duration_no_frame_cap(tmp_path):
    video_path = tmp_path / "synthetic2.mp4"
    _make_synthetic_video(video_path, n_frames=37, fps=12.0, size=(128, 96))
    zone = Zone(zone_id="z2", video_id="v2", label="Zone", shape="polygon", points=[(0.1, 0.1), (0.9, 0.1), (0.5, 0.9)])
    output_path = tmp_path / "out2.mp4"

    result = ZonePipeline().run(video_path, zone, output_path)
    assert result.video_info.frame_count == 37
    assert result.metrics["frames_read"] == 37
    assert result.metrics["frames_written"] == 37
