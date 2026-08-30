"""Person tracker for Target Person ID: ultralytics' real BoT-SORT (Kalman
filter + camera-motion compensation + fused IoU/appearance matching),
constructed directly (not through the model.track()/YAML convenience path)
so a custom OSNet ReID encoder can be plugged into its appearance-matching
step. This reuses vetted, already-installed tracking code (ultralytics ships
a complete BoT-SORT at ultralytics.trackers.bot_sort) instead of
reimplementing Kalman/GMC/association -- see the plan's research section for
why the official BoT-SORT/FastReID repo was rejected in favor of this.

Two things this wrapper provides that the generic ObjectTracker doesn't:
1. A real appearance (ReID) signal fused into association, not just IoU.
2. predicted_bbox(track_id): BoT-SORT's own Kalman filter keeps predicting a
   track's position even while it's "Lost" (occluded, within track_buffer
   frames) -- this is what lets the red box survive occlusion by prediction
   rather than disappearing the instant a detection is missed.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from ultralytics import YOLO
from ultralytics.trackers.bot_sort import BOTSORT
from ultralytics.utils import IterableSimpleNamespace

from backend.modules.person_id.person_reid import PersonReID


@dataclass
class PersonTrack:
    track_id: int
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float
    predicted: bool = False  # True if this position came from Kalman prediction (occluded), not a real detection


class _EmptyBoxes:
    """Duck-typed zero-detection stand-in for ultralytics' Boxes, for frames
    skipped by detection_stride -- existing tracks still get Kalman-predicted
    forward via BOTSORT.update()'s own multi_predict() call, they just have no
    new detection to match against this frame."""

    conf = np.zeros((0,), dtype=np.float32)
    xywh = np.zeros((0, 4), dtype=np.float32)
    cls = np.zeros((0,), dtype=np.float32)


def _xywh_to_xyxy_int(row: np.ndarray, width: int, height: int) -> tuple[int, int, int, int]:
    cx, cy, w, h = row[:4]
    x1, y1 = cx - w / 2, cy - h / 2
    x2, y2 = cx + w / 2, cy + h / 2
    return (
        max(0, int(x1)), max(0, int(y1)),
        min(width, int(x2)), min(height, int(y2)),
    )


class PersonBotSortTracker:
    def __init__(
        self,
        model_path: str,
        reid: PersonReID,
        detection_stride: int = 1,
        confidence: float = 0.35,
        track_buffer: int = 30,
        # Library default (0.8) verified against this project's own measured
        # embedding separation: cosine distance/2 for same-person crops was
        # ~0.062, different-person ~0.265-0.31 -- the 0.8 threshold (which
        # requires distance/2 <= 1-0.8 = 0.2) cleanly separates the two.
        appearance_thresh: float = 0.8,
        frame_rate: int = 30,
        device: str | None = None,
    ) -> None:
        self._model = YOLO(model_path)
        self.confidence = confidence
        self.device = device
        self.detection_stride = max(1, detection_stride)
        self._frame_index = 0
        self.detection_count = 0  # frames where real YOLO detection actually ran (for benchmarking)

        args = IterableSimpleNamespace(
            track_high_thresh=0.25, track_low_thresh=0.1, new_track_thresh=0.25,
            track_buffer=track_buffer, match_thresh=0.8, fuse_score=True,
            gmc_method="sparseOptFlow",
            proximity_thresh=0.5, appearance_thresh=appearance_thresh,
            with_reid=True, model="auto",  # "auto"/model unused -- .encoder is replaced below
        )
        self._tracker = BOTSORT(args, frame_rate=frame_rate)
        self._tracker.encoder = self._make_encoder(reid)

    def _make_encoder(self, reid: PersonReID):
        def encoder(img: np.ndarray, dets: np.ndarray) -> list[np.ndarray]:
            h, w = img.shape[:2]
            crops = []
            for row in dets:
                x1, y1, x2, y2 = _xywh_to_xyxy_int(row, w, h)
                crop = img[y1:y2, x1:x2] if x2 > x1 and y2 > y1 else None
                crops.append(crop)
            embeddings = reid.embed_batch(crops)
            dim = next((e.shape[0] for e in embeddings if e is not None), 512)
            return [e if e is not None else np.zeros(dim, dtype=np.float32) for e in embeddings]

        return encoder

    def update(self, frame: np.ndarray) -> list[PersonTrack]:
        """Runs YOLO person detection only every detection_stride frames;
        BOTSORT's own Kalman filter propagates existing tracks on the frames
        in between (see _EmptyBoxes above)."""
        do_detect = self._frame_index % self.detection_stride == 0
        self._frame_index += 1

        if do_detect:
            self.detection_count += 1
            result = self._model.predict(
                frame, classes=[0], conf=self.confidence, device=self.device, verbose=False,
            )[0]
            boxes = result.boxes.cpu().numpy() if result.boxes is not None else _EmptyBoxes()
        else:
            boxes = _EmptyBoxes()

        raw = self._tracker.update(boxes, frame)
        tracks = []
        for row in raw:
            x1, y1, x2, y2, track_id, score = row[0], row[1], row[2], row[3], int(row[4]), float(row[5])
            tracks.append(PersonTrack(track_id=track_id, bbox=(int(x1), int(y1), int(x2), int(y2)), confidence=score))
        return tracks

    def predicted_bbox(self, track_id: int) -> tuple[int, int, int, int] | None:
        """Kalman-predicted position of a track currently in BOTSORT's own
        lost_stracks (occluded/undetected but within track_buffer frames) --
        used to keep drawing the red box through a short occlusion instead of
        letting it disappear the instant a real detection is missed."""
        for t in self._tracker.lost_stracks:
            if t.track_id == track_id:
                x1, y1, x2, y2 = t.xyxy
                return (int(x1), int(y1), int(x2), int(y2))
        return None

    def reset(self) -> None:
        self._tracker.reset()
        self._frame_index = 0
