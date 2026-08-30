"""Integration-lite test: runs the real BehaviorPipeline (real YOLO tracker,
real video I/O, real ZoneMonitor reuse) end-to-end on a tiny synthetic clip.
Genuine behavior-triggering verification (real tracked people, real
evidence files) is covered by the real-video smoke test - a synthetic noise
clip has no trackable objects, so this proves the plumbing (full duration,
zone reuse, progress reporting) rather than actual detections.
"""
import cv2
import numpy as np

from backend.modules.behavior.pipeline import BehaviorPipeline
from backend.modules.zone.geometry import Zone


def _make_synthetic_video(path, n_frames=10, fps=10.0, size=(160, 120)):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, size)
    rng = np.random.default_rng(0)
    for _ in range(n_frames):
        frame = rng.integers(0, 255, (size[1], size[0], 3), dtype=np.uint8)
        writer.write(frame)
    writer.release()


def test_pipeline_runs_full_duration_with_zone_and_progress(tmp_path):
    video_path = tmp_path / "synthetic.mp4"
    _make_synthetic_video(video_path, n_frames=12, fps=10.0, size=(160, 120))

    zone = Zone(zone_id="bz1", video_id="v1", label="Zone", shape="rectangle", points=[(0.1, 0.1), (0.9, 0.9)])
    output_path = tmp_path / "out.mp4"
    progress_values = []

    result = BehaviorPipeline().run(
        video_path, output_path, zone=zone, target_track_id=99,
        progress_cb=progress_values.append,
    )

    assert result.output_video_path == output_path
    assert result.video_info.frame_count == 12
    assert result.metrics["frames_read"] == 12
    assert result.metrics["frames_written"] == 12
    assert progress_values[-1] == 1.0
    assert isinstance(result.event_counts, dict)  # no crash even with zero real objects

    cap = cv2.VideoCapture(str(output_path))
    assert cap.isOpened()
    assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 12
    cap.release()


def test_pipeline_saves_evidence_directory(tmp_path):
    video_path = tmp_path / "synthetic2.mp4"
    _make_synthetic_video(video_path, n_frames=6, fps=10.0, size=(128, 96))
    output_path = tmp_path / "out2.mp4"
    evidence_dir = tmp_path / "evidence"

    result = BehaviorPipeline().run(video_path, output_path, evidence_dir=evidence_dir)
    assert result.evidence_dir == evidence_dir
    assert evidence_dir.is_dir()  # created even if empty (no real objects in synthetic noise)
