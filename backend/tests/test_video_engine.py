"""Video engine tests using small synthetic clips generated on the fly -
no external fixture files needed, so these run anywhere.
"""
import cv2
import numpy as np
import pytest

from backend.core.output import OutputVideoWriter
from backend.core.video import VideoInfo, VideoOpenError, VideoReader


def _make_synthetic_video(path, n_frames=20, fps=10.0, size=(64, 48)):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, size)
    for i in range(n_frames):
        frame = np.full((size[1], size[0], 3), i % 255, dtype=np.uint8)
        writer.write(frame)
    writer.release()


def test_video_reader_reports_correct_info_and_yields_every_frame(tmp_path):
    video_path = tmp_path / "synthetic.mp4"
    _make_synthetic_video(video_path, n_frames=20, fps=10.0, size=(64, 48))

    with VideoReader(video_path) as reader:
        assert reader.info.width == 64
        assert reader.info.height == 48
        assert abs(reader.info.fps - 10.0) < 0.5
        assert reader.info.frame_count == 20

        frames = list(reader)
        assert len(frames) == 20
        assert [f.index for f in frames] == list(range(20))
        # no arbitrary 90-frame cap - the full clip (however short) comes through
        assert frames[-1].index == 19
        assert reader.metrics.frames_read == 20


def test_video_reader_missing_file_raises():
    with pytest.raises(VideoOpenError):
        VideoReader("this/path/does/not/exist.mp4")


def test_output_writer_produces_playable_video_with_matching_duration(tmp_path):
    src = tmp_path / "synthetic.mp4"
    _make_synthetic_video(src, n_frames=30, fps=15.0, size=(80, 60))

    with VideoReader(src) as reader:
        out_path = tmp_path / "out.mp4"
        writer = OutputVideoWriter(out_path, reader.info)
        for frame in reader:
            writer.write(frame.image)
        writer.close()

        assert writer.frames_written == 30
        assert writer.open_result.codec_used  # something was selected

    # re-open the produced file and sanity-check duration/fps/frame count
    cap = cv2.VideoCapture(str(out_path))
    assert cap.isOpened()
    out_fps = cap.get(cv2.CAP_PROP_FPS)
    out_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    assert abs(out_fps - 15.0) < 0.5
    assert out_frames == 30


def test_output_writer_resizes_mismatched_frames(tmp_path):
    info = VideoInfo(path=tmp_path / "x.mp4", fps=10.0, width=64, height=48, frame_count=5, duration_sec=0.5)
    writer = OutputVideoWriter(tmp_path / "resized.mp4", info)
    wrong_size_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    writer.write(wrong_size_frame)  # must not raise despite size mismatch
    writer.close()
    assert writer.frames_written == 1
