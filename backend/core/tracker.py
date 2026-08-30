"""Detection + tracking wrapper around Ultralytics YOLO + ByteTrack.

This is the one place that runs the per-frame detector and turns its output
into stable track ids. Modules (person_id, anpr, zone, behavior) consume
Track objects instead of talking to ultralytics directly.

Performance note: full YOLO+ByteTrack inference is by far the dominant cost
in every pipeline (benchmarked ~75-90% of per-frame time depending on which
other modules are active). TrackerConfig.detection_stride lets a caller run
the real detector only every Nth frame and propagate tracks between samples
via simple linear velocity extrapolation - cheap (pure arithmetic, no model
call) and bounded (never extrapolates more than stride-1 frames before the
next real detection resyncs everything). Default stride=1 means "detect
every frame", byte-for-byte the original behavior - this is opt-in, not a
default change, so every existing caller/test is unaffected unless it
explicitly sets a larger stride.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from ultralytics import YOLO

from backend.config import TrackerConfig


@dataclass
class Track:
    track_id: int
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2 in pixel coords
    class_id: int
    confidence: float
    propagated: bool = False  # True if this frame's box was extrapolated, not detected

    @property
    def center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


class ObjectTracker:
    """Persistent-state YOLO+ByteTrack tracker for a single video's lifetime.

    Create one instance per video processing run (persist=True tracking
    state is tied to the underlying ultralytics predictor and must not be
    shared across unrelated videos).
    """

    def __init__(self, config: TrackerConfig, class_ids: tuple[int, ...] | None = None):
        self.config = config
        self.class_ids = list(class_ids) if class_ids is not None else None
        self._model = YOLO(str(config.model_path))
        self._frame_index = 0
        self._last_tracks: dict[int, Track] = {}
        self._velocity: dict[int, tuple[float, float, float, float]] = {}

    def update(self, image: np.ndarray) -> list[Track]:
        stride = max(1, self.config.detection_stride)
        do_detect = self._frame_index % stride == 0
        self._frame_index += 1

        if do_detect:
            tracks = self._detect(image)
            self._remember(tracks)
            return tracks
        return self._propagate(image.shape[1], image.shape[0])

    def _detect(self, image: np.ndarray) -> list[Track]:
        results = self._model.track(
            image,
            persist=True,
            tracker=self.config.tracker_yaml,
            conf=self.config.confidence,
            iou=self.config.iou,
            classes=self.class_ids,
            device=self.config.device,
            verbose=False,
        )
        tracks: list[Track] = []
        if not results:
            return tracks
        boxes = results[0].boxes
        if boxes is None or boxes.id is None:
            return tracks  # detections with no assigned track id are dropped

        ids = boxes.id.int().cpu().tolist()
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().tolist()
        clss = boxes.cls.int().cpu().tolist()

        for tid, box, conf, cls in zip(ids, xyxy, confs, clss):
            x1, y1, x2, y2 = box
            tracks.append(
                Track(
                    track_id=int(tid),
                    bbox=(int(x1), int(y1), int(x2), int(y2)),
                    class_id=int(cls),
                    confidence=float(conf),
                )
            )
        return tracks

    def _remember(self, tracks: list[Track]) -> None:
        """Records this real detection as the baseline for propagation, and
        the per-track velocity (bbox delta) since the previous real
        detection - used to extrapolate position on skipped frames."""
        new_velocity: dict[int, tuple[float, float, float, float]] = {}
        for t in tracks:
            prev = self._last_tracks.get(t.track_id)
            if prev is not None:
                px1, py1, px2, py2 = prev.bbox
                x1, y1, x2, y2 = t.bbox
                new_velocity[t.track_id] = (x1 - px1, y1 - py1, x2 - px2, y2 - py2)
            else:
                new_velocity[t.track_id] = (0.0, 0.0, 0.0, 0.0)
        self._last_tracks = {t.track_id: t for t in tracks}
        self._velocity = new_velocity

    def _propagate(self, width: int, height: int) -> list[Track]:
        """Extrapolates each track's last known box forward by its recorded
        velocity - no model inference. A track that has genuinely left frame
        or stopped existing will drift briefly (at most stride-1 frames)
        until the next real detection corrects or drops it; downstream
        consumers (TargetLock/ZoneMonitor/BehaviorMonitor) already tolerate
        exactly this kind of brief inconsistency by design."""
        propagated: list[Track] = []
        for tid, t in self._last_tracks.items():
            dx1, dy1, dx2, dy2 = self._velocity.get(tid, (0.0, 0.0, 0.0, 0.0))
            x1, y1, x2, y2 = t.bbox
            nx1, ny1, nx2, ny2 = x1 + dx1, y1 + dy1, x2 + dx2, y2 + dy2
            nx1, nx2 = max(0.0, min(width, nx1)), max(0.0, min(width, nx2))
            ny1, ny2 = max(0.0, min(height, ny1)), max(0.0, min(height, ny2))
            if nx2 <= nx1 or ny2 <= ny1:
                continue
            new_track = Track(
                track_id=tid, bbox=(int(nx1), int(ny1), int(nx2), int(ny2)),
                class_id=t.class_id, confidence=t.confidence, propagated=True,
            )
            propagated.append(new_track)
            self._last_tracks[tid] = new_track  # so the NEXT propagated frame extrapolates further, not from the same stale point
        return propagated
