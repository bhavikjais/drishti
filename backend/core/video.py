"""Shared video engine: reading, frame sampling, timestamps, metrics.

Every module pipeline (person_id, anpr, zone, behavior, lowlight) reads
frames through VideoReader and writes the annotated result through
core.output.OutputVideoWriter, instead of touching cv2.VideoCapture /
cv2.VideoWriter directly. This keeps codec fallback, FPS/duration handling,
and processing metrics in one place.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np


@dataclass(frozen=True)
class VideoInfo:
    path: Path
    fps: float
    width: int
    height: int
    frame_count: int
    duration_sec: float

    @property
    def resolution(self) -> tuple[int, int]:
        return (self.width, self.height)


@dataclass
class Frame:
    index: int
    timestamp_sec: float
    image: np.ndarray


@dataclass
class ProcessingMetrics:
    frames_read: int = 0
    frames_written: int = 0
    started_at: float = 0.0
    finished_at: float = 0.0

    @property
    def elapsed_sec(self) -> float:
        end = self.finished_at or time.monotonic()
        return max(0.0, end - self.started_at)

    @property
    def processing_fps(self) -> float:
        if self.elapsed_sec <= 0:
            return 0.0
        return self.frames_read / self.elapsed_sec

    def as_dict(self) -> dict:
        return {
            "frames_read": self.frames_read,
            "frames_written": self.frames_written,
            "elapsed_sec": round(self.elapsed_sec, 3),
            "processing_fps": round(self.processing_fps, 2),
        }


class VideoOpenError(RuntimeError):
    pass


class VideoReader:
    """Opens an uploaded video and yields every frame with an index/timestamp.

    Full videos are processed by default - there is no frame-count cap.
    Callers that only need periodic work (face recognition, OCR, ...) decide
    their own sampling cadence against Frame.index; VideoReader itself always
    yields every frame so tracking stays smooth and the output video can be
    written frame-for-frame.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.exists():
            raise VideoOpenError(f"video file not found: {self.path}")

        self._cap = cv2.VideoCapture(str(self.path))
        if not self._cap.isOpened():
            raise VideoOpenError(f"OpenCV could not open video: {self.path}")

        fps = self._cap.get(cv2.CAP_PROP_FPS) or 0.0
        if fps <= 0.1:
            fps = 25.0  # sane fallback for malformed containers
        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_count = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if frame_count > 0 else 0.0

        self.info = VideoInfo(
            path=self.path,
            fps=fps,
            width=width,
            height=height,
            frame_count=frame_count,
            duration_sec=duration,
        )
        self.metrics = ProcessingMetrics()

    def __iter__(self) -> Iterator[Frame]:
        self.metrics.started_at = time.monotonic()
        index = 0
        while True:
            ok, image = self._cap.read()
            if not ok:
                break
            timestamp = index / self.info.fps
            self.metrics.frames_read += 1
            yield Frame(index=index, timestamp_sec=timestamp, image=image)
            index += 1
        self.metrics.finished_at = time.monotonic()

    def close(self) -> None:
        self._cap.release()

    def __enter__(self) -> "VideoReader":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def extract_frame(path: str | Path, fraction: float = 0.5) -> tuple[np.ndarray, VideoInfo]:
    """Grabs one representative frame at `fraction` of the video's duration
    (0.0 = first frame, 0.5 = middle, 1.0 = last) - used to hand the UI a
    frame to draw a zone on. Cheap: opens the file, seeks once, reads once.
    """
    fraction = min(1.0, max(0.0, fraction))
    reader = VideoReader(path)
    try:
        target_index = min(reader.info.frame_count - 1, int(round(fraction * (reader.info.frame_count - 1))))
        target_index = max(0, target_index)
        cap = reader._cap
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_index)
        ok, image = cap.read()
        if not ok:
            # fall back to a linear scan from the start if seeking landed badly
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            image = None
            for _ in range(target_index + 1):
                ok, frame = cap.read()
                if not ok:
                    break
                image = frame
            if image is None:
                raise VideoOpenError(f"could not read any frame from {path}")
        return image, reader.info
    finally:
        reader.close()
