"""Combined multi-module pipeline: the ONE production entry point that lets
a user enable any subset of {person_id, anpr, zone(s), behavior, lowlight}
on a single uploaded video and get ONE output video + ONE event stream back.

This exists because each module's own pipeline.py (person_id/anpr/zone/
behavior) independently opens its own VideoReader and its own
ObjectTracker. That's fine for standalone/single-module use (and those
pipelines are kept as-is, still directly usable and still covered by their
own regression tests), but naively running several of them back-to-back on
the same video would mean multiple full video decodes AND multiple YOLO
inference passes for what should be one job. This module runs exactly ONE
VideoReader + ONE ObjectTracker pass and feeds every enabled module's
existing, already-tested logic (TargetLock, PlateAggregator, ZoneMonitor,
BehaviorMonitor, core.lowlight) from that single pass - no detection logic
is reimplemented here, only composed.

Two integration-only event types are synthesized here (not inside any
module, since neither zone/state.py nor person_id/anpr know about each
other): TARGET_ZONE_INTRUSION (the locked target track entered a zone) and
a one-shot LOW_LIGHT notification (the run contained dark footage).
TARGET_BEHAVIOR_ALERT already exists inside behavior/state.py and is reused
as-is by passing it the real target_track_id/zone_states from this run.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2

from backend.config import (
    AnprConfig, BehaviorConfig, LowLightConfig, OSNET_MODEL_PATH, PersonIDConfig, TrackerConfig,
    YUNET_MODEL_PATH, SFACE_MODEL_PATH, ZoneConfig,
)
from backend.core.lowlight import process_frame as lowlight_process_frame
from backend.core.output import (
    CYAN, MAGENTA, ORANGE, OutputVideoWriter, draw_banner, draw_polygon,
    draw_target_box, format_timestamp,
)
from backend.core.target_lock import TargetLock
from backend.core.tracker import ObjectTracker
from backend.core.video import VideoInfo, VideoReader
from backend.modules.anpr.aggregator import PlateAggregator
from backend.modules.anpr.ocr import PlateOcr, normalize_plate, plates_match
from backend.modules.anpr.plate_detector import PlateDetector
from backend.modules.anpr.validate import is_plausible_plate
from backend.modules.behavior.state import BehaviorMonitor
from backend.modules.person_id.custom_tracker import PersonBotSortTracker
from backend.modules.person_id.detector import FaceDetector
from backend.modules.person_id.person_reid import PersonReID
from backend.modules.person_id.pipeline import _bbox_min_side, _prediction_still_looks_like_target
from backend.modules.person_id.recognizer import FaceRecognizer, ReferenceSet
from backend.modules.person_id.target_gallery import TargetGallery
from backend.modules.zone.geometry import Zone, centroid, denormalize_polygon, footpoint
from backend.modules.zone.state import INSIDE, ZoneMonitor

_BEHAVIOR_BANNER_COLOR = {
    "LOITERING": ORANGE, "SUDDEN_DIRECTION_CHANGE": ORANGE,
    "ABNORMAL_SPEED": ORANGE, "REPEATED_BACK_AND_FORTH": ORANGE,
    "TARGET_BEHAVIOR_ALERT": (0, 0, 220),
}
_BEHAVIOR_LABEL = {
    "LOITERING": "LOITERING", "SUDDEN_DIRECTION_CHANGE": "SUDDEN DIRECTION CHANGE",
    "ABNORMAL_SPEED": "ABNORMAL SPEED", "REPEATED_BACK_AND_FORTH": "REPEATED PACING",
}


def _pad_bbox(bbox: tuple[int, int, int, int], pad_frac: float, w: int, h: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = bbox
    bw, bh = x2 - x1, y2 - y1
    px, py = int(bw * pad_frac), int(bh * pad_frac)
    return (max(0, x1 - px), max(0, y1 - py), min(w, x2 + px), min(h, y2 + py))


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _find_shared_track_for_bbox(
    bbox: tuple[int, int, int, int], tracks_by_id: dict, class_id: int, min_iou: float = 0.3,
) -> int | None:
    """The dedicated person_id BoT-SORT tracker and the shared multi-class
    ObjectTracker used by zone/behavior are two independent trackers with two
    independent track-id spaces (their id counters aren't related, and could
    coincidentally collide on the same integer for unrelated people). This
    spatially correlates the person_id target's current bbox against the
    shared tracker's own person tracks THIS FRAME (by IoU, not by id) so
    TARGET_ZONE_INTRUSION/TARGET_BEHAVIOR_ALERT -- which are keyed off the
    shared tracker's ids -- keep working when person_id is combined with
    zone/behavior in the same job."""
    best_tid, best_iou = None, min_iou
    for tid, t in tracks_by_id.items():
        if t.class_id != class_id:
            continue
        score = _iou(bbox, t.bbox)
        if score > best_iou:
            best_tid, best_iou = tid, score
    return best_tid


@dataclass
class OrchestratorRequest:
    enable_person_id: bool = False
    reference_photo_paths: list[Path] = field(default_factory=list)
    person_id_config: PersonIDConfig | None = None
    snapshot_path: Path | None = None

    enable_anpr: bool = False
    target_plate: str | None = None
    anpr_config: AnprConfig | None = None

    zones: list[Zone] = field(default_factory=list)
    zone_config: ZoneConfig | None = None

    enable_behavior: bool = False
    behavior_config: BehaviorConfig | None = None

    enable_lowlight: bool = False
    lowlight_config: LowLightConfig | None = None

    tracker_config: TrackerConfig | None = None
    evidence_dir: Path | None = None


@dataclass
class OrchestratorResult:
    output_video_path: Path
    codec_used: str
    browser_playable: bool
    video_info: VideoInfo
    metrics: dict
    events: list[dict]
    modules_run: list[str]
    person_id: dict | None = None
    anpr: dict | None = None
    zones: list[dict] | None = None
    behavior: dict | None = None
    lowlight: dict | None = None
    evidence_dir: Path | None = None


class OrchestratorError(RuntimeError):
    pass


class CombinedPipeline:
    def __init__(self, request: OrchestratorRequest):
        self.req = request
        self.tracker_config = request.tracker_config or TrackerConfig()

        self.person_id_cfg = request.person_id_config or PersonIDConfig()
        self.anpr_cfg = request.anpr_config or AnprConfig()
        self.zone_cfg = request.zone_config or ZoneConfig()
        self.behavior_cfg = request.behavior_config or BehaviorConfig()
        self.lowlight_cfg = request.lowlight_config or LowLightConfig()

        self.face_detector = self.face_recognizer = self.person_reid = None
        if request.enable_person_id:
            self.face_detector = FaceDetector(YUNET_MODEL_PATH)
            self.face_recognizer = FaceRecognizer(SFACE_MODEL_PATH)
            self.person_reid = PersonReID(OSNET_MODEL_PATH)

        self.plate_detector = self.ocr = None
        if request.enable_anpr:
            self.plate_detector = PlateDetector()
            self.ocr = PlateOcr()

    def _needed_class_ids(self) -> tuple[int, ...] | None:
        """person_id no longer needs the shared tracker at all -- it runs its
        own dedicated PersonBotSortTracker (see run()). The shared tracker is
        still needed for anpr (vehicle classes) and, independently, for
        zone/behavior's own generic person+vehicle tracking (unrelated to
        person_id's target -- see _find_shared_track_for_bbox for how the two
        are bridged when combined)."""
        req = self.req
        ids: set[int] = set()
        if req.enable_anpr:
            ids.update(self.tracker_config.vehicle_class_ids)
        if req.zones or req.enable_behavior:
            ids.add(self.tracker_config.person_class_id)
            ids.update(self.tracker_config.vehicle_class_ids)
        return tuple(sorted(ids)) if ids else None

    def run(self, video_path: str | Path, output_path: str | Path, progress_cb: Callable[[float], None] | None = None) -> OrchestratorResult:
        req = self.req
        modules_run = []
        if req.enable_person_id:
            modules_run.append("person_id")
        if req.enable_anpr:
            modules_run.append("anpr")
        if req.zones:
            modules_run.append("zone")
        if req.enable_behavior:
            modules_run.append("behavior")
        if req.enable_lowlight:
            modules_run.append("lowlight")
        if not modules_run:
            raise OrchestratorError("at least one module must be enabled")

        class_ids = self._needed_class_ids()
        tracker = ObjectTracker(self.tracker_config, class_ids=class_ids) if class_ids else None

        # --- person_id state ---
        reference_set = None
        person_lock = None
        person_min_votes = None
        saved_snapshot = None
        person_gallery = None
        person_tracker: PersonBotSortTracker | None = None  # constructed below, once fps is known
        if req.enable_person_id:
            if not req.reference_photo_paths:
                raise OrchestratorError("person_id enabled but no reference photos provided")
            reference_set = ReferenceSet(req.reference_photo_paths, self.face_detector, self.face_recognizer)
            if reference_set.usable_count == 0:
                raise OrchestratorError(f"no usable face found in any reference photo: {reference_set.rejected}")
            person_min_votes = PersonIDConfig.resolve_votes(self.person_id_cfg.min_reference_votes, reference_set.usable_count)
            person_lock = TargetLock(
                confirmation_observations=self.person_id_cfg.confirmation_observations,
                gap_tolerance_frames=self.person_id_cfg.gap_tolerance_frames,
                event_confirmed="TARGET_CONFIRMED", event_reacquired="TARGET_REACQUIRED", event_lost="TARGET_LOST",
            )
            person_gallery = TargetGallery(max_size=self.person_id_cfg.gallery_max_size)

        # --- anpr state ---
        aggregator = None
        anpr_lock = None
        normalized_target = None
        vehicle_seen: set[int] = set()
        plate_localized_seen: set[int] = set()
        plate_confirmed_seen: set[int] = set()
        anpr_extra_events: list[dict] = []
        if req.enable_anpr:
            normalized_target = normalize_plate(req.target_plate) if req.target_plate else None
            aggregator = PlateAggregator(self.anpr_cfg.max_observations_per_track, self.anpr_cfg.vote_min_observations, self.anpr_cfg.confirm_min_mean_confidence)
            if normalized_target:
                anpr_lock = TargetLock(
                    confirmation_observations=self.anpr_cfg.search_confirmation_observations,
                    gap_tolerance_frames=self.anpr_cfg.gap_tolerance_frames,
                    event_confirmed="TARGET_VEHICLE_FOUND", event_reacquired="TARGET_VEHICLE_REACQUIRED", event_lost="TARGET_VEHICLE_LOST",
                )

        # --- zone state (multiple zones supported) ---
        zone_monitors = [ZoneMonitor(z.zone_id, self.zone_cfg.entry_grace_frames, self.zone_cfg.exit_grace_frames, self.zone_cfg.track_absence_grace_frames, self.zone_cfg.dwell_threshold_sec) for z in req.zones]
        zone_polygons_px: list[list[tuple[int, int]]] = []

        # --- behavior state ---
        behavior_monitor = BehaviorMonitor(self.behavior_cfg) if req.enable_behavior else None

        # --- evidence / annotation bookkeeping ---
        evidence_dir = req.evidence_dir
        if evidence_dir is not None:
            evidence_dir = Path(evidence_dir)
            evidence_dir.mkdir(parents=True, exist_ok=True)
        active_banners: list[tuple[list[str], tuple[int, int, int], int]] = []
        behavior_alert_until: dict[int, int] = {}
        track_class: dict[int, int] = {}
        low_light_notified = False
        low_light_frame_count = 0
        enhanced_frame_count = 0
        person_face_inference_count = 0
        person_reid_inference_count = 0
        person_predicted_frame_count = 0
        all_events: list[dict] = []
        target_zone_intrusion_last: dict[int, float] = {}
        event_seq = 0

        def next_event_id() -> str:
            nonlocal event_seq
            event_seq += 1
            return f"evt_{event_seq}"

        def save_evidence(frame_image, track_id, event_type, frame_index, bbox=None) -> str | None:
            if evidence_dir is None or track_id is None:
                return None
            if bbox is not None:
                x1, y1, x2, y2 = (max(0, v) for v in bbox)
                crop = frame_image[y1:y2, x1:x2]
            else:
                crop = frame_image
            if crop is None or crop.size == 0:
                return None
            fname = f"{track_id}_{event_type}_{frame_index}.jpg"
            path = evidence_dir / fname
            if cv2.imwrite(str(path), crop):
                return str(path)
            return None

        with VideoReader(video_path) as reader:
            writer = OutputVideoWriter(output_path, reader.info)
            h, w = reader.info.height, reader.info.width
            for zone in req.zones:
                zone_polygons_px.append(denormalize_polygon(zone.normalized_polygon(), w, h))
            banner_frames = max(1, int(round(reader.info.fps * max(self.zone_cfg.banner_display_sec, self.behavior_cfg.alert_display_sec))))
            progress_stride = max(1, reader.info.frame_count // 100) if reader.info.frame_count else 30

            if req.enable_person_id:
                # Dedicated tracker for the target -- see _needed_class_ids()'s
                # docstring for why this is separate from the shared `tracker`
                # above rather than folded into it (real BoT-SORT+OSNet vs the
                # shared generic multi-class ByteTrack tracker are structurally
                # different trackers; this is the exact same PersonBotSortTracker
                # class the standalone, already-tested PersonIDPipeline uses).
                person_tracker = PersonBotSortTracker(
                    model_path=str(self.tracker_config.model_path),
                    reid=self.person_reid,
                    detection_stride=self.tracker_config.detection_stride,
                    confidence=self.tracker_config.confidence,
                    track_buffer=self.person_id_cfg.gap_tolerance_frames,
                    frame_rate=max(1, round(reader.info.fps)) if reader.info.fps else 30,
                    device=self.tracker_config.device,
                )

            try:
                for frame in reader:
                    if req.enable_lowlight:
                        frame.image, ll_info = lowlight_process_frame(frame.image, self.lowlight_cfg)
                        if ll_info.classification == "LOW_LIGHT":
                            low_light_frame_count += 1
                            if not low_light_notified:
                                low_light_notified = True
                                all_events.append({
                                    "event_id": next_event_id(), "type": "LOW_LIGHT", "track_id": None,
                                    "frame_index": frame.index, "timestamp_sec": frame.timestamp_sec,
                                    "data": {"backend": ll_info.backend_used, "note": "low-light footage detected in this video"},
                                })
                        if ll_info.enhanced:
                            enhanced_frame_count += 1

                    tracks_by_id = {}
                    if tracker is not None:
                        tracks = tracker.update(frame.image)
                        tracks_by_id = {t.track_id: t for t in tracks}
                        for tid, t in tracks_by_id.items():
                            track_class[tid] = t.class_id

                    person_target_bbox = None
                    anpr_target_tid = None

                    # ---------------- person_id (dedicated BoT-SORT+OSNet tracker) ----------------
                    if req.enable_person_id:
                        person_tracks = person_tracker.update(frame.image)
                        person_tracks_by_id = {t.track_id: t for t in person_tracks}

                        # face recognition: identity CONFIRMATION (periodic, not continuous)
                        if frame.index % self.person_id_cfg.face_sample_stride == 0:
                            for tid, track in person_tracks_by_id.items():
                                if person_lock.confirmed and tid == person_lock.target_track_id:
                                    continue
                                cx1, cy1, cx2, cy2 = _pad_bbox(track.bbox, self.person_id_cfg.crop_pad_frac, w, h)
                                crop = frame.image[cy1:cy2, cx1:cx2]
                                if crop.size == 0:
                                    continue
                                face = self.face_detector.best(crop)
                                if face is None:
                                    continue
                                person_face_inference_count += 1
                                probe = self.face_recognizer.embed(crop, face)
                                votes, best_sim = reference_set.vote(probe, self.person_id_cfg.similarity_threshold)
                                if votes < person_min_votes:
                                    continue
                                was_confirmed = person_lock.confirmed
                                person_lock.register_match(tid, frame.index, frame.timestamp_sec, votes, round(best_sim, 3))
                                if not was_confirmed and person_lock.confirmed:
                                    if req.snapshot_path is not None and not saved_snapshot:
                                        if cv2.imwrite(str(req.snapshot_path), crop):
                                            saved_snapshot = Path(req.snapshot_path)
                                    save_evidence(frame.image, tid, "TARGET_CONFIRMED", frame.index, track.bbox)

                        # person ReID: identity MAINTENANCE -- what survives a turned-away
                        # face or occlusion, which face recognition alone cannot do.
                        if frame.index % self.person_id_cfg.reid_sample_stride == 0 and person_tracks_by_id:
                            reid_candidates = list(person_tracks_by_id.items())
                            crops = [frame.image[max(0, t.bbox[1]):t.bbox[3], max(0, t.bbox[0]):t.bbox[2]] for _, t in reid_candidates]
                            embeddings = self.person_reid.embed_batch(crops)
                            person_reid_inference_count += sum(1 for e in embeddings if e is not None)
                            for (tid, track), embedding in zip(reid_candidates, embeddings):
                                if embedding is None:
                                    continue
                                good_bbox = _bbox_min_side(track.bbox) >= self.person_id_cfg.min_bbox_side_for_gallery
                                if person_lock.confirmed and tid == person_lock.target_track_id:
                                    if good_bbox:
                                        person_gallery.add(embedding)
                                    continue
                                if len(person_gallery) == 0 or not good_bbox:
                                    continue
                                reid_sim = person_gallery.best_similarity(embedding)
                                if reid_sim >= self.person_id_cfg.reid_similarity_threshold:
                                    person_lock.register_match(tid, frame.index, frame.timestamp_sec, votes=1, similarity=round(reid_sim, 3))

                        # box position: real detection, or Kalman-predicted (capped +
                        # appearance-verified -- see pipeline.py's docstring for why
                        # geometry alone drifts onto the wrong person after a genuine gap)
                        visible_tid = person_lock.step_visibility(set(person_tracks_by_id.keys()), frame.index, frame.timestamp_sec)
                        if visible_tid is not None:
                            person_target_bbox = person_tracks_by_id[visible_tid].bbox
                        elif (
                            person_lock.confirmed
                            and person_lock.target_track_id is not None
                            and person_lock.frames_since_seen <= self.person_id_cfg.max_prediction_frames
                        ):
                            predicted = person_tracker.predicted_bbox(person_lock.target_track_id)
                            if predicted is not None:
                                looks_ok, did_infer = _prediction_still_looks_like_target(
                                    frame.image, predicted, person_gallery, self.person_reid,
                                    self.person_id_cfg.reid_similarity_threshold,
                                )
                                if did_infer:
                                    person_reid_inference_count += 1
                                if looks_ok:
                                    person_target_bbox = predicted
                                    person_predicted_frame_count += 1

                    # ---------------- anpr ----------------
                    if req.enable_anpr:
                        for tid in tracks_by_id:
                            if track_class.get(tid) in self.tracker_config.vehicle_class_ids and tid not in vehicle_seen:
                                vehicle_seen.add(tid)
                                all_events.append({"event_id": next_event_id(), "type": "VEHICLE_DETECTED", "track_id": tid, "frame_index": frame.index, "timestamp_sec": frame.timestamp_sec, "data": {}})

                        do_sample = frame.index % self.anpr_cfg.ocr_sample_stride == 0
                        if do_sample and self.ocr.available:
                            for tid, track in tracks_by_id.items():
                                if track.class_id not in self.tracker_config.vehicle_class_ids:
                                    continue
                                existing = aggregator.aggregate(tid)
                                saturated = existing is not None and existing.confirmed and aggregator.observation_count(tid) >= self.anpr_cfg.max_observations_per_track
                                if saturated:
                                    continue
                                x1, y1, x2, y2 = track.bbox
                                crop = frame.image[max(0, y1):y2, max(0, x1):x2]
                                ch, cw = crop.shape[:2] if crop.size else (0, 0)
                                if cw < self.anpr_cfg.min_vehicle_width or ch < self.anpr_cfg.min_vehicle_height:
                                    continue
                                candidate = self.plate_detector.locate(crop)
                                if candidate is None:
                                    continue
                                if tid not in plate_localized_seen:
                                    plate_localized_seen.add(tid)
                                    all_events.append({"event_id": next_event_id(), "type": "PLATE_DETECTED", "track_id": tid, "frame_index": frame.index, "timestamp_sec": frame.timestamp_sec, "data": {}})
                                px1, py1, px2, py2 = candidate.bbox
                                text, confidence = self.ocr.read(crop[py1:py2, px1:px2])
                                if text is None or confidence is None or confidence < self.anpr_cfg.min_read_confidence:
                                    continue
                                if not is_plausible_plate(text):
                                    continue
                                aggregator.add_observation(tid, text, confidence, frame.index, frame.timestamp_sec)
                                agg = aggregator.aggregate(tid)
                                if agg is not None:
                                    if agg.confirmed and tid not in plate_confirmed_seen:
                                        plate_confirmed_seen.add(tid)
                                        all_events.append({"event_id": next_event_id(), "type": "PLATE_CONFIRMED", "track_id": tid, "frame_index": frame.index, "timestamp_sec": frame.timestamp_sec, "data": {"text": agg.text, "confidence": agg.mean_confidence}, "plate": agg.text, "confidence": agg.mean_confidence, "evidence_path": save_evidence(frame.image, tid, "PLATE_CONFIRMED", frame.index, track.bbox)})
                                if anpr_lock is not None:
                                    is_match, similarity = plates_match(text, normalized_target, self.anpr_cfg.search_match_threshold, self.anpr_cfg.search_match_max_len_diff)
                                    if is_match:
                                        anpr_lock.register_match(tid, frame.index, frame.timestamp_sec, votes=1, similarity=similarity)

                        if anpr_lock is not None:
                            visible_tid = anpr_lock.step_visibility(set(tid for tid in tracks_by_id if track_class.get(tid) in self.tracker_config.vehicle_class_ids), frame.index, frame.timestamp_sec)
                            if visible_tid is not None:
                                anpr_target_tid = visible_tid

                    # target_tid_shared: the SHARED tracker's id for whichever physical
                    # person/vehicle is the target, used only to correlate against
                    # zone/behavior (which are keyed off the shared tracker's own id
                    # space). person_id's dedicated tracker has a completely separate id
                    # space, so its target is bridged spatially (IoU) rather than by id.
                    target_tid_shared = None
                    if person_target_bbox is not None and tracks_by_id:
                        target_tid_shared = _find_shared_track_for_bbox(
                            person_target_bbox, tracks_by_id, self.tracker_config.person_class_id,
                        )
                    elif anpr_target_tid is not None:
                        target_tid_shared = anpr_target_tid

                    # ---------------- zone(s) ----------------
                    zone_inside_any: dict[int, str] = {}
                    if req.zones:
                        footpoints = {tid: footpoint(t.bbox) for tid, t in tracks_by_id.items()}
                        for zone, monitor, polygon_px in zip(req.zones, zone_monitors, zone_polygons_px):
                            n_before = len(monitor.events)
                            monitor.update(footpoints, frame.index, frame.timestamp_sec, polygon_px)
                            new_events = monitor.events[n_before:]
                            for ev in new_events:
                                d = {"event_id": next_event_id(), "type": ev.type, "track_id": ev.track_id, "frame_index": ev.frame_index, "timestamp_sec": ev.timestamp_sec, "zone": zone.zone_id, "data": ev.data}
                                if ev.type in ("ZONE_ENTRY", "ZONE_EXIT", "LONG_DWELL"):
                                    d["evidence_path"] = save_evidence(frame.image, ev.track_id, ev.type, frame.index, tracks_by_id[ev.track_id].bbox if ev.track_id in tracks_by_id else None)
                                all_events.append(d)
                                cname = "VEHICLE" if track_class.get(ev.track_id) in self.tracker_config.vehicle_class_ids else "PERSON"
                                if ev.type == "ZONE_ENTRY":
                                    active_banners.append((["ZONE ENTRY", f"{cname} #{ev.track_id}", format_timestamp(ev.timestamp_sec)], ORANGE, frame.index + banner_frames))
                                elif ev.type == "ZONE_EXIT":
                                    active_banners.append((["ZONE EXIT", f"{cname} #{ev.track_id}", format_timestamp(ev.timestamp_sec)], (60, 200, 60), frame.index + banner_frames))
                                elif ev.type == "LONG_DWELL":
                                    active_banners.append((["LONG DWELL", f"{cname} #{ev.track_id}", f"Duration: {ev.data['duration_sec']:.1f} sec"], (0, 0, 200), frame.index + banner_frames))
                                if ev.type == "ZONE_ENTRY" and target_tid_shared is not None and ev.track_id == target_tid_shared:
                                    last = target_zone_intrusion_last.get(ev.track_id, -1e9)
                                    if ev.timestamp_sec - last >= self.behavior_cfg.behavior_cooldown_seconds:
                                        target_zone_intrusion_last[ev.track_id] = ev.timestamp_sec
                                        all_events.append({"event_id": next_event_id(), "type": "TARGET_ZONE_INTRUSION", "track_id": ev.track_id, "frame_index": ev.frame_index, "timestamp_sec": ev.timestamp_sec, "zone": zone.zone_id, "data": {}, "evidence_path": save_evidence(frame.image, ev.track_id, "TARGET_ZONE_INTRUSION", frame.index, tracks_by_id[ev.track_id].bbox if ev.track_id in tracks_by_id else None)})
                            for tid in tracks_by_id:
                                if monitor.state_of(tid) == INSIDE:
                                    zone_inside_any[tid] = INSIDE

                    # ---------------- behavior ----------------
                    if req.enable_behavior:
                        centroids = {tid: centroid(t.bbox) for tid, t in tracks_by_id.items()}
                        zone_states_for_behavior = {tid: zone_inside_any.get(tid, "OUTSIDE") for tid in tracks_by_id} if req.zones else None
                        zone_id_for_behavior = req.zones[0].zone_id if req.zones else None
                        new_events = behavior_monitor.update(centroids, frame.index, frame.timestamp_sec, zone_states=zone_states_for_behavior, zone_id=zone_id_for_behavior, target_track_id=target_tid_shared)
                        for ev in new_events:
                            cname = "VEHICLE" if track_class.get(ev.track_id) in self.tracker_config.vehicle_class_ids else "PERSON"
                            d = {"event_id": next_event_id(), "type": ev.type, "track_id": ev.track_id, "frame_index": ev.frame_index, "timestamp_sec": ev.timestamp_sec, "data": ev.data}
                            d["evidence_path"] = save_evidence(frame.image, ev.track_id, ev.type, frame.index, tracks_by_id[ev.track_id].bbox if ev.track_id in tracks_by_id else None)
                            all_events.append(d)
                            behavior_alert_until[ev.track_id] = frame.index + banner_frames
                            if ev.type == "TARGET_BEHAVIOR_ALERT":
                                lines = ["TARGET BEHAVIOR ALERT", f"{cname} #{ev.track_id}", ev.data["trigger_behavior"]]
                            else:
                                lines = ["BEHAVIOR ALERT", f"{_BEHAVIOR_LABEL[ev.type]} - {cname} #{ev.track_id}", format_timestamp(ev.timestamp_sec)]
                            active_banners.append((lines, _BEHAVIOR_BANNER_COLOR[ev.type], frame.index + banner_frames))

                    # ---------------- annotation ----------------
                    for polygon_px, zone in zip(zone_polygons_px, req.zones):
                        draw_polygon(frame.image, polygon_px, label=zone.label or "RESTRICTED ZONE")

                    drawn: set[int] = set()
                    if person_target_bbox is not None:
                        # Drawn from the dedicated person_id tracker's own bbox (real
                        # detection or Kalman-predicted) -- NOT from tracks_by_id, which
                        # is a different tracker with a different id space entirely.
                        draw_target_box(frame.image, person_target_bbox, label="TARGET")
                        if target_tid_shared is not None:
                            drawn.add(target_tid_shared)  # don't also draw a zone/behavior box on the same physical person
                    elif anpr_target_tid is not None and anpr_target_tid in tracks_by_id:
                        agg = aggregator.aggregate(anpr_target_tid) if aggregator else None
                        label = ["TARGET VEHICLE", agg.text if agg else normalized_target, f"{round(agg.mean_confidence) if agg else 0}%"]
                        draw_target_box(frame.image, tracks_by_id[anpr_target_tid].bbox, label=label)
                        drawn.add(anpr_target_tid)

                    if req.enable_anpr and not req.target_plate:
                        for tid, track in tracks_by_id.items():
                            if tid in drawn or track.class_id not in self.tracker_config.vehicle_class_ids:
                                continue
                            agg = aggregator.aggregate(tid)
                            if agg is not None and agg.confirmed:
                                draw_target_box(frame.image, track.bbox, label=[agg.text, f"{round(agg.mean_confidence)}%"], color=CYAN)
                                drawn.add(tid)

                    for tid in zone_inside_any:
                        if tid in drawn or tid not in tracks_by_id:
                            continue
                        cname = "VEHICLE" if track_class.get(tid) in self.tracker_config.vehicle_class_ids else "PERSON"
                        draw_target_box(frame.image, tracks_by_id[tid].bbox, label=f"{cname} #{tid}", color=ORANGE, thickness=2)
                        drawn.add(tid)

                    for tid, until in behavior_alert_until.items():
                        if tid in drawn or frame.index >= until or tid not in tracks_by_id:
                            continue
                        cname = "VEHICLE" if track_class.get(tid) in self.tracker_config.vehicle_class_ids else "PERSON"
                        draw_target_box(frame.image, tracks_by_id[tid].bbox, label=f"{cname} #{tid}", color=MAGENTA, thickness=2)
                        drawn.add(tid)

                    active_banners = [b for b in active_banners if b[2] > frame.index]
                    for slot, (lines, color, _exp) in enumerate(active_banners):
                        draw_banner(frame.image, lines, color, slot=slot)

                    writer.write(frame.image)
                    if progress_cb is not None and (frame.index % progress_stride == 0) and reader.info.frame_count:
                        progress_cb(min(1.0, frame.index / reader.info.frame_count))

            finally:
                writer.close()
            reader.metrics.frames_written = writer.frames_written
            metrics = reader.metrics.as_dict()
            video_info = reader.info

        if progress_cb is not None:
            progress_cb(1.0)

        # TargetLock (person_id/anpr search) computes its own confirm/lost/
        # reacquire events internally but - unlike zone/behavior, which
        # append into all_events as they happen - those were never merged
        # in. Do it once here now that the run is complete.
        if person_lock is not None:
            for e in person_lock.events:
                all_events.append({"event_id": next_event_id(), "type": e.type, "track_id": e.track_id, "frame_index": e.frame_index, "timestamp_sec": e.timestamp_sec, "data": e.data})
        if anpr_lock is not None:
            for e in anpr_lock.events:
                all_events.append({"event_id": next_event_id(), "type": e.type, "track_id": e.track_id, "frame_index": e.frame_index, "timestamp_sec": e.timestamp_sec, "data": e.data})
        all_events.sort(key=lambda d: d["frame_index"])

        person_id_summary = None
        if req.enable_person_id:
            person_id_summary = {
                "confirmed": person_lock.confirmed, "target_track_id": person_lock.target_track_id,
                "first_seen_sec": person_lock.first_seen_sec, "last_seen_sec": person_lock.last_seen_sec,
                "visible_duration_sec": person_lock.visible_duration_sec, "visible_frame_count": person_lock.visible_frame_count,
                "reference_usable_count": reference_set.usable_count, "min_reference_votes_used": person_min_votes,
                "snapshot_path": str(saved_snapshot) if saved_snapshot else None,
                "face_inference_count": person_face_inference_count,
                "reid_inference_count": person_reid_inference_count,
                "detector_inference_count": person_tracker.detection_count if person_tracker else 0,
                "predicted_frame_count": person_predicted_frame_count,
            }

        anpr_summary = None
        if req.enable_anpr:
            detected_plates = [
                {"track_id": tid, "text": agg.text, "mean_confidence": agg.mean_confidence, "observation_count": agg.observation_count, "confirmed": agg.confirmed}
                for tid in aggregator.all_track_ids() if (agg := aggregator.aggregate(tid)) is not None
            ]
            target_summary = None
            if anpr_lock is not None:
                match_conf = None
                if anpr_lock.target_track_id is not None:
                    agg = aggregator.aggregate(anpr_lock.target_track_id)
                    match_conf = agg.mean_confidence if agg else None
                target_summary = {
                    "found": anpr_lock.confirmed, "track_id": anpr_lock.target_track_id,
                    "plate_text": normalized_target if anpr_lock.confirmed else None, "match_confidence": match_conf,
                    "first_seen_sec": anpr_lock.first_seen_sec, "last_seen_sec": anpr_lock.last_seen_sec,
                    "visible_duration_sec": anpr_lock.visible_duration_sec, "visible_frame_count": anpr_lock.visible_frame_count,
                }
            anpr_summary = {"mode": "search" if normalized_target else "automatic", "searched_plate": normalized_target, "target": target_summary, "detected_plates": detected_plates, "vehicles_detected": len(vehicle_seen), "ocr_status": self.ocr.status.to_dict()}

        zones_summary = None
        if req.zones:
            zones_summary = []
            for zone, monitor in zip(req.zones, zone_monitors):
                entries = sum(1 for e in monitor.events if e.type == "ZONE_ENTRY")
                exits = sum(1 for e in monitor.events if e.type == "ZONE_EXIT")
                dwells = sum(1 for e in monitor.events if e.type == "LONG_DWELL")
                zones_summary.append({"zone_id": zone.zone_id, "label": zone.label, "entries": entries, "exits": exits, "dwell_events": dwells})

        behavior_summary = None
        if req.enable_behavior:
            counts: dict[str, int] = {}
            for e in behavior_monitor.events:
                counts[e.type] = counts.get(e.type, 0) + 1
            behavior_summary = {"event_counts": counts, "tracks_observed": len(track_class)}

        lowlight_summary = None
        if req.enable_lowlight:
            total = video_info.frame_count or 1
            lowlight_summary = {
                "low_light_detected": low_light_frame_count > 0, "enhancement_applied": enhanced_frame_count > 0,
                "backend": self.lowlight_cfg.backend, "low_light_frames": low_light_frame_count,
                "enhanced_frames": enhanced_frame_count, "enhanced_percentage": round(100.0 * enhanced_frame_count / total, 2),
            }

        return OrchestratorResult(
            output_video_path=Path(output_path), codec_used=writer.open_result.codec_used, browser_playable=writer.open_result.browser_playable,
            video_info=video_info, metrics=metrics, events=all_events, modules_run=modules_run,
            person_id=person_id_summary, anpr=anpr_summary, zones=zones_summary, behavior=behavior_summary, lowlight=lowlight_summary,
            evidence_dir=evidence_dir,
        )
