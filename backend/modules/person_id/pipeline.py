"""Target person identification + continuous tracking pipeline.

Flow per uploaded video:
  1. Build face embeddings for every usable reference photo (1-6 supported) --
     this establishes WHO the target is.
  2. Run YOLO person detection + a real BoT-SORT tracker (Kalman filter,
     camera-motion compensation, IoU+appearance fused matching -- see
     custom_tracker.py) on every frame; detection itself only runs every
     detection_stride frames, the tracker's own Kalman filter propagates
     existing tracks on the frames in between.
  3. On a periodic cadence, run YuNet+SFace face recognition (identity
     confirmation) and, independently, OSNet person-ReID (continuous
     identity MAINTENANCE -- this is what survives a turned-away face or a
     brief occlusion, which face recognition alone cannot do).
  4. Feed matching observations into TargetLock, which owns confirmation /
     occlusion-tolerance / re-acquisition state (target_lock.py -- kept
     separate so that state machine is unit-testable without real video or
     CV models).
  5. Draw exactly one red box on the target every frame it's visible OR
     Kalman-predicted (occluded but within the tracker's own track_buffer) --
     this is the non-negotiable continuous-tracking requirement: the box
     must not depend on face recognition firing that frame.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from backend.config import (
    LowLightConfig, OSNET_MODEL_PATH, PersonIDConfig, SFACE_MODEL_PATH, TrackerConfig, YUNET_MODEL_PATH,
)
from backend.core.lowlight import process_frame as lowlight_process_frame
from backend.core.output import OutputVideoWriter, draw_target_box
from backend.core.target_lock import TargetLock
from backend.core.video import VideoInfo, VideoReader
from backend.modules.person_id.custom_tracker import PersonBotSortTracker
from backend.modules.person_id.detector import FaceDetector
from backend.modules.person_id.person_reid import PersonReID
from backend.modules.person_id.recognizer import FaceRecognizer, ReferenceSet
from backend.modules.person_id.target_gallery import TargetGallery

logger = logging.getLogger(__name__)


class PersonIDError(RuntimeError):
    pass


@dataclass
class PersonIDResult:
    confirmed: bool
    target_track_id: int | None
    first_seen_sec: float | None
    last_seen_sec: float | None
    visible_duration_sec: float
    visible_frame_count: int
    output_video_path: Path
    codec_used: str
    browser_playable: bool
    video_info: VideoInfo
    metrics: dict
    events: list[dict]
    reference_usable_count: int
    reference_rejected: list[tuple[Path, str]]
    min_reference_votes_used: int
    snapshot_path: Path | None = None
    lowlight_stats: dict | None = None
    # Inference-frequency counters -- for the "measure, don't just claim, FPS
    # and per-stage cost" requirement.
    face_inference_count: int = 0
    reid_inference_count: int = 0
    detector_inference_count: int = 0
    predicted_frame_count: int = 0  # frames where the box came from Kalman prediction, not a real detection


def _pad_bbox(bbox: tuple[int, int, int, int], pad_frac: float, w: int, h: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = bbox
    bw, bh = x2 - x1, y2 - y1
    px, py = int(bw * pad_frac), int(bh * pad_frac)
    return (max(0, x1 - px), max(0, y1 - py), min(w, x2 + px), min(h, y2 + py))


def _bbox_min_side(bbox: tuple[int, int, int, int]) -> int:
    x1, y1, x2, y2 = bbox
    return min(x2 - x1, y2 - y1)


def _prediction_still_looks_like_target(
    frame_image: np.ndarray,
    predicted_bbox: tuple[int, int, int, int],
    gallery: TargetGallery,
    reid: PersonReID,
    threshold: float,
) -> tuple[bool, bool]:
    """Geometry alone (pure linear-velocity Kalman prediction) is not enough
    to trust a box during a gap -- measured on real footage, it can drift
    onto an unrelated person within just a handful of frames once the target
    genuinely leaves frame, well before max_prediction_frames would otherwise
    cut it off. This is the "combine motion + appearance" requirement in
    practice: before drawing a predicted box, verify the predicted region
    still resembles the target's own appearance gallery. If the gallery is
    empty (shouldn't happen once tracking has run for a while, but guard
    anyway) there's no better signal available, so geometry alone is trusted.

    Returns (looks_like_target, did_run_inference) -- the second value lets
    the caller track reid_inference_count accurately.
    """
    if len(gallery) == 0:
        return True, False
    x1, y1, x2, y2 = predicted_bbox
    crop = frame_image[max(0, y1):y2, max(0, x1):x2]
    if crop.size == 0:
        return False, False
    probe = reid.embed(crop)
    if probe is None:
        return False, True
    return gallery.best_similarity(probe) >= threshold, True


class PersonIDPipeline:
    def __init__(self, config: PersonIDConfig | None = None, tracker_config: TrackerConfig | None = None):
        self.config = config or PersonIDConfig()
        self.tracker_config = tracker_config or TrackerConfig()
        self.face_detector = FaceDetector(YUNET_MODEL_PATH)
        self.face_recognizer = FaceRecognizer(SFACE_MODEL_PATH)
        self.reid = PersonReID(OSNET_MODEL_PATH)

    def run(
        self,
        video_path: str | Path,
        reference_photo_paths: list[str | Path],
        output_path: str | Path,
        snapshot_path: str | Path | None = None,
        lowlight_config: LowLightConfig | None = None,
    ) -> PersonIDResult:
        """lowlight_config is opt-in and defaults to None (disabled) so
        existing callers/behavior are unaffected. When provided, every frame
        is classified and, if genuinely dark, enhanced in place BEFORE face
        detection/recognition and BEFORE it's written to the output video -
        so detection benefits from the enhanced image and there's no risk of
        enhancing evidence twice or writing an unenhanced frame."""
        if not reference_photo_paths:
            raise PersonIDError("at least one reference photo is required")
        if len(reference_photo_paths) > 6:
            raise PersonIDError("at most 6 reference photos are supported")

        reference_set = ReferenceSet(reference_photo_paths, self.face_detector, self.face_recognizer)
        if reference_set.usable_count == 0:
            raise PersonIDError(
                f"no usable face found in any of {len(reference_photo_paths)} reference photo(s): "
                f"{reference_set.rejected}"
            )
        min_votes = PersonIDConfig.resolve_votes(self.config.min_reference_votes, reference_set.usable_count)
        logger.info(
            "PersonID: %d/%d reference photos usable, min_reference_votes resolved to %d",
            reference_set.usable_count, len(reference_photo_paths), min_votes,
        )

        cfg = self.config
        lock = TargetLock(
            confirmation_observations=cfg.confirmation_observations,
            gap_tolerance_frames=cfg.gap_tolerance_frames,
        )
        gallery = TargetGallery(max_size=cfg.gallery_max_size)
        saved_snapshot: Path | None = None
        lowlight_enhanced_count = 0
        lowlight_lowlight_count = 0
        face_inference_count = 0
        reid_inference_count = 0
        predicted_frame_count = 0
        was_tracking_prev_frame = False  # for TARGET_TRACKING / TEMPORARILY_LOST / LEFT_FRAME event edges

        with VideoReader(video_path) as reader:
            writer = OutputVideoWriter(output_path, reader.info)
            h, w = reader.info.height, reader.info.width
            tracker = PersonBotSortTracker(
                model_path=str(self.tracker_config.model_path),
                reid=self.reid,
                # Deliberately NOT self.tracker_config.detection_stride (3):
                # BOTSORT/ByteTrack removes any not-yet-activated track that
                # goes unmatched on a single update() call, and a skipped
                # (_EmptyBoxes) frame always offers zero detections to match
                # against - so with stride>1, a newly-detected person's track
                # gets destroyed on the very next frame, before it can ever
                # earn the second hit that activates it. Only a track born on
                # the tracker's literal first frame is exempt (ByteTrack's
                # frame_id==1 special case), which is why stride>1 here
                # silently tracked almost nobody. Detecting every frame avoids
                # this path entirely - see PersonBotSortTracker's docstring.
                detection_stride=1,
                confidence=self.tracker_config.confidence,
                track_buffer=cfg.gap_tolerance_frames,
                device=self.tracker_config.device,
            )

            for frame in reader:
                if lowlight_config is not None:
                    frame.image, ll_info = lowlight_process_frame(frame.image, lowlight_config)
                    if ll_info.classification == "LOW_LIGHT":
                        lowlight_lowlight_count += 1
                    if ll_info.enhanced:
                        lowlight_enhanced_count += 1

                tracks = tracker.update(frame.image)
                tracks_by_id = {t.track_id: t for t in tracks}

                # ---------------- face recognition: identity CONFIRMATION ----------------
                do_face_sample = frame.index % cfg.face_sample_stride == 0
                if do_face_sample:
                    for tid, track in tracks_by_id.items():
                        if lock.confirmed and tid == lock.target_track_id:
                            continue  # already the locked target, no need to re-verify
                        crop_box = _pad_bbox(track.bbox, cfg.crop_pad_frac, w, h)
                        cx1, cy1, cx2, cy2 = crop_box
                        crop = frame.image[cy1:cy2, cx1:cx2]
                        if crop.size == 0:
                            continue
                        face = self.face_detector.best(crop)
                        if face is None:
                            continue
                        face_inference_count += 1
                        probe_embedding = self.face_recognizer.embed(crop, face)
                        votes, best_sim = reference_set.vote(probe_embedding, cfg.similarity_threshold)
                        if votes < min_votes:
                            continue

                        was_confirmed = lock.confirmed
                        lock.register_match(tid, frame.index, frame.timestamp_sec, votes, round(best_sim, 3))
                        if not was_confirmed and lock.confirmed and snapshot_path is not None and not saved_snapshot:
                            ok = cv2.imwrite(str(snapshot_path), crop)
                            if ok:
                                saved_snapshot = Path(snapshot_path)

                # ---------------- person ReID: identity MAINTENANCE ----------------
                # This is what keeps the target's identity attached to their body
                # when the face is turned away, too small, or occluded -- face
                # recognition alone cannot do this (the whole point of this rebuild).
                do_reid_sample = frame.index % cfg.reid_sample_stride == 0
                if do_reid_sample and tracks_by_id:
                    reid_candidates = [
                        (tid, track) for tid, track in tracks_by_id.items()
                        if not (lock.confirmed and tid == lock.target_track_id and lock.frames_since_seen == 0)
                        # (still ReID the current target too, when it's the one that just
                        # got occluded/reacquired, so the gallery keeps accumulating fresh
                        # appearance -- only skip when it's trivially the same, already-
                        # fresh-this-frame target with nothing new to learn)
                    ] or list(tracks_by_id.items())
                    crops = [frame.image[max(0, t.bbox[1]):t.bbox[3], max(0, t.bbox[0]):t.bbox[2]] for _, t in reid_candidates]
                    embeddings = self.reid.embed_batch(crops)
                    reid_inference_count += sum(1 for e in embeddings if e is not None)

                    for (tid, track), embedding in zip(reid_candidates, embeddings):
                        if embedding is None:
                            continue
                        good_bbox = _bbox_min_side(track.bbox) >= cfg.min_bbox_side_for_gallery

                        if lock.confirmed and tid == lock.target_track_id:
                            # Confirmed, currently-tracked target: safe to grow the
                            # gallery -- track continuity already vouches for identity,
                            # gated only on crop quality (section 6/12: never add from an
                            # uncertain/candidate association, only from the track we
                            # already trust).
                            if good_bbox:
                                gallery.add(embedding)
                            continue

                        # Candidate track: only usable for RE-ACQUISITION once the
                        # gallery has something to compare against, and only above
                        # the measured similarity threshold -- never seeds/replaces
                        # the gallery itself from an uncertain candidate.
                        if len(gallery) == 0 or not good_bbox:
                            continue
                        reid_sim = gallery.best_similarity(embedding)
                        if reid_sim >= cfg.reid_similarity_threshold:
                            lock.register_match(tid, frame.index, frame.timestamp_sec, votes=1, similarity=round(reid_sim, 3))

                # ---------------- box drawing: real position, or Kalman-predicted ----------------
                visible_tid = lock.step_visibility(set(tracks_by_id.keys()), frame.index, frame.timestamp_sec)
                is_tracking_this_frame = False
                if visible_tid is not None:
                    draw_target_box(frame.image, tracks_by_id[visible_tid].bbox, label="TARGET")
                    is_tracking_this_frame = True
                elif (
                    lock.confirmed
                    and lock.target_track_id is not None
                    and lock.frames_since_seen <= cfg.max_prediction_frames
                ):
                    # Not in this frame's real detections, but not yet declared
                    # genuinely LOST either (still within gap_tolerance_frames) --
                    # this is the non-negotiable requirement: keep the box on
                    # screen via the tracker's own Kalman prediction, not just on
                    # frames the detector/face-recognizer happened to fire.
                    # Capped at max_prediction_frames (far shorter than
                    # gap_tolerance_frames): a pure linear-velocity prediction
                    # bridges a brief occlusion well but drifts onto an unrelated
                    # person once the target has genuinely left frame -- past
                    # this cap the box is hidden rather than guessed, until a
                    # real detection or ReID/face match reacquires it.
                    predicted = tracker.predicted_bbox(lock.target_track_id)
                    if predicted is not None:
                        looks_ok, did_infer = _prediction_still_looks_like_target(
                            frame.image, predicted, gallery, self.reid, cfg.reid_similarity_threshold,
                        )
                        if did_infer:
                            reid_inference_count += 1
                        if looks_ok:
                            draw_target_box(frame.image, predicted, label="TARGET")
                            predicted_frame_count += 1
                            is_tracking_this_frame = True

                if is_tracking_this_frame and not was_tracking_prev_frame:
                    lock.events.append(_edge_event("TARGET_TRACKING", lock, frame))
                elif not is_tracking_this_frame and was_tracking_prev_frame and lock.confirmed:
                    event_type = "TARGET_LEFT_FRAME" if tracker.predicted_bbox(lock.target_track_id) is None else "TARGET_TEMPORARILY_LOST"
                    lock.events.append(_edge_event(event_type, lock, frame))
                was_tracking_prev_frame = is_tracking_this_frame

                writer.write(frame.image)

            lock.end()
            writer.close()
            reader.metrics.frames_written = writer.frames_written
            metrics = reader.metrics.as_dict()
            video_info = reader.info

        return PersonIDResult(
            confirmed=lock.confirmed,
            target_track_id=lock.target_track_id,
            first_seen_sec=lock.first_seen_sec,
            last_seen_sec=lock.last_seen_sec,
            visible_duration_sec=lock.visible_duration_sec,
            visible_frame_count=lock.visible_frame_count,
            output_video_path=Path(output_path),
            codec_used=writer.open_result.codec_used,
            browser_playable=writer.open_result.browser_playable,
            video_info=video_info,
            metrics=metrics,
            events=[e.__dict__ for e in lock.events],
            reference_usable_count=reference_set.usable_count,
            reference_rejected=reference_set.rejected,
            min_reference_votes_used=min_votes,
            snapshot_path=saved_snapshot,
            face_inference_count=face_inference_count,
            reid_inference_count=reid_inference_count,
            detector_inference_count=tracker.detection_count,
            predicted_frame_count=predicted_frame_count,
            lowlight_stats=(
                {
                    "low_light_detected": lowlight_lowlight_count > 0,
                    "enhancement_applied": lowlight_enhanced_count > 0,
                    "backend": lowlight_config.backend,
                    "low_light_frames": lowlight_lowlight_count,
                    "enhanced_frames": lowlight_enhanced_count,
                    "enhanced_percentage": round(100.0 * lowlight_enhanced_count / video_info.frame_count, 2) if video_info.frame_count else 0.0,
                }
                if lowlight_config is not None else None
            ),
        )


def _edge_event(event_type: str, lock: TargetLock, frame) -> "LockEvent":
    from backend.core.target_lock import LockEvent

    return LockEvent(event_type, lock.target_track_id, frame.index, frame.timestamp_sec)
