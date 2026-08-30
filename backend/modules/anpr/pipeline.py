"""ANPR pipeline: automatic plate reading, and Mode 2 plate search.

Flow per uploaded video:
  1. Run YOLO+ByteTrack vehicle detection/tracking on every frame.
  2. On a periodic sampling cadence, localize + OCR each active vehicle
     track's plate. Every read feeds PlateAggregator (multi-frame voting -
     see aggregator.py for why a single bad frame can't win).
  3. Automatic mode (no searched plate): draw a neutral labeled box on any
     track whose aggregate has reached CONFIRMED.
  4. Search mode (a plate was requested): compare each individual OCR read
     against the normalized target via ocr.plates_match; matching reads feed
     a TargetLock (the same confirmation/occlusion-tolerance/re-acquisition
     state machine person_id uses) so the red box only locks after multiple
     independently-matching frames and never jumps to a different vehicle.
  5. Emit deduplicated events (VEHICLE_DETECTED, PLATE_DETECTED, PLATE_READ,
     PLATE_CONFIRMED, TARGET_VEHICLE_FOUND/LOST/REACQUIRED) - track-keyed,
     one-shot or state-transition gated, never per-frame spam.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from backend.config import AnprConfig, LowLightConfig, TrackerConfig
from backend.core.events import EventBus
from backend.core.lowlight import process_frame as lowlight_process_frame
from backend.core.output import CYAN, OutputVideoWriter, draw_target_box
from backend.core.target_lock import TargetLock
from backend.core.tracker import ObjectTracker
from backend.core.video import VideoInfo, VideoReader
from backend.modules.anpr.aggregator import PlateAggregator
from backend.modules.anpr.ocr import PlateOcr, normalize_plate, plates_match
from backend.modules.anpr.plate_detector import PlateDetector
from backend.modules.anpr.validate import is_plausible_plate


@dataclass
class DetectedPlate:
    track_id: int
    text: str
    mean_confidence: float
    observation_count: int
    confirmed: bool


@dataclass
class TargetVehicleResult:
    found: bool
    track_id: int | None
    plate_text: str | None
    match_confidence: float | None  # OCR mean confidence (0-100) of the matched plate
    first_seen_sec: float | None
    last_seen_sec: float | None
    visible_duration_sec: float
    visible_frame_count: int


@dataclass
class AnprResult:
    mode: str  # "automatic" | "search"
    searched_plate: str | None
    target: TargetVehicleResult | None
    detected_plates: list[DetectedPlate]
    vehicles_detected: int
    output_video_path: Path
    codec_used: str
    browser_playable: bool
    video_info: VideoInfo
    metrics: dict
    events: list[dict]
    ocr_status: dict
    lowlight_stats: dict | None = None


class AnprPipeline:
    def __init__(self, config: AnprConfig | None = None, tracker_config: TrackerConfig | None = None):
        self.config = config or AnprConfig()
        self.tracker_config = tracker_config or TrackerConfig()
        self.plate_detector = PlateDetector()
        self.ocr = PlateOcr()

    def run(
        self,
        video_path: str | Path,
        output_path: str | Path,
        target_plate: str | None = None,
        lowlight_config: LowLightConfig | None = None,
    ) -> AnprResult:
        """lowlight_config is opt-in (default None = disabled, unchanged
        behavior). When provided, each frame is enhanced in place (if
        genuinely dark) BEFORE the vehicle crop is sliced from it - so the
        plate crop OCR reads is already enhanced with no separate crop-level
        enhancement step, and the existing per-track OCR sampling/caching
        (do_sample, aggregator saturation check) is untouched, so a dark
        plate still isn't re-enhanced/re-OCR'd more often than it would
        otherwise be sampled."""
        cfg = self.config
        normalized_target = normalize_plate(target_plate) if target_plate else None
        search_mode = bool(normalized_target)

        tracker = ObjectTracker(self.tracker_config, class_ids=self.tracker_config.vehicle_class_ids)
        aggregator = PlateAggregator(cfg.max_observations_per_track, cfg.vote_min_observations, cfg.confirm_min_mean_confidence)
        events = EventBus()

        lock = None
        if search_mode:
            lock = TargetLock(
                confirmation_observations=cfg.search_confirmation_observations,
                gap_tolerance_frames=cfg.gap_tolerance_frames,
                event_confirmed="TARGET_VEHICLE_FOUND",
                event_reacquired="TARGET_VEHICLE_REACQUIRED",
                event_lost="TARGET_VEHICLE_LOST",
            )

        vehicle_seen: set[int] = set()
        plate_localized_seen: set[int] = set()
        plate_confirmed_seen: set[int] = set()
        lowlight_enhanced_count = 0
        lowlight_lowlight_count = 0

        with VideoReader(video_path) as reader:
            writer = OutputVideoWriter(output_path, reader.info)

            for frame in reader:
                if lowlight_config is not None:
                    frame.image, ll_info = lowlight_process_frame(frame.image, lowlight_config)
                    if ll_info.classification == "LOW_LIGHT":
                        lowlight_lowlight_count += 1
                    if ll_info.enhanced:
                        lowlight_enhanced_count += 1

                tracks = tracker.update(frame.image)
                tracks_by_id = {t.track_id: t for t in tracks}

                for tid in tracks_by_id:
                    if tid not in vehicle_seen:
                        vehicle_seen.add(tid)
                        events.emit("VEHICLE_DETECTED", tid, frame.index, frame.timestamp_sec, cooldown_sec=float("inf"))

                do_sample = frame.index % cfg.ocr_sample_stride == 0
                if do_sample and self.ocr.available:
                    for tid, track in tracks_by_id.items():
                        existing = aggregator.aggregate(tid)
                        saturated = (
                            existing is not None and existing.confirmed
                            and aggregator.observation_count(tid) >= cfg.max_observations_per_track
                        )
                        if saturated:
                            continue

                        x1, y1, x2, y2 = track.bbox
                        crop = frame.image[max(0, y1):y2, max(0, x1):x2]
                        h, w = crop.shape[:2] if crop.size else (0, 0)
                        if w < cfg.min_vehicle_width or h < cfg.min_vehicle_height:
                            continue

                        candidate = self.plate_detector.locate(crop)
                        if candidate is None:
                            continue
                        if tid not in plate_localized_seen:
                            plate_localized_seen.add(tid)
                            events.emit("PLATE_DETECTED", tid, frame.index, frame.timestamp_sec, cooldown_sec=float("inf"))

                        px1, py1, px2, py2 = candidate.bbox
                        plate_crop = crop[py1:py2, px1:px2]
                        text, confidence = self.ocr.read(plate_crop)
                        if text is None or confidence is None or confidence < cfg.min_read_confidence:
                            continue
                        if not is_plausible_plate(text):
                            # Obvious OCR noise ("A", "SW", "123") never even
                            # becomes a vote -- a single garbage read can't
                            # accidentally win a close aggregation race.
                            continue

                        aggregator.add_observation(tid, text, confidence, frame.index, frame.timestamp_sec)
                        agg = aggregator.aggregate(tid)
                        if agg is not None:
                            events.emit(
                                "PLATE_READ", tid, frame.index, frame.timestamp_sec,
                                cooldown_sec=float("inf"), state=agg.text,
                                text=agg.text, confidence=agg.mean_confidence,
                            )
                            if agg.confirmed and tid not in plate_confirmed_seen:
                                plate_confirmed_seen.add(tid)
                                events.emit(
                                    "PLATE_CONFIRMED", tid, frame.index, frame.timestamp_sec,
                                    cooldown_sec=float("inf"), text=agg.text,
                                    confidence=agg.mean_confidence, observations=agg.observation_count,
                                )

                        if search_mode and lock is not None:
                            is_match, similarity = plates_match(
                                text, normalized_target, cfg.search_match_threshold, cfg.search_match_max_len_diff,
                            )
                            if is_match:
                                lock.register_match(tid, frame.index, frame.timestamp_sec, votes=1, similarity=similarity)

                if search_mode and lock is not None:
                    visible_tid = lock.step_visibility(set(tracks_by_id.keys()), frame.index, frame.timestamp_sec)
                    if visible_tid is not None:
                        agg = aggregator.aggregate(visible_tid)
                        plate_text = agg.text if agg else normalized_target
                        conf_pct = round(agg.mean_confidence) if agg else 0
                        draw_target_box(
                            frame.image, tracks_by_id[visible_tid].bbox,
                            label=["TARGET VEHICLE", plate_text, f"{conf_pct}%"],
                        )
                else:
                    for tid, track in tracks_by_id.items():
                        agg = aggregator.aggregate(tid)
                        if agg is not None and agg.confirmed:
                            draw_target_box(
                                frame.image, track.bbox,
                                label=[agg.text, f"{round(agg.mean_confidence)}%"],
                                color=CYAN,
                            )

                writer.write(frame.image)

            writer.close()
            reader.metrics.frames_written = writer.frames_written
            metrics = reader.metrics.as_dict()
            video_info = reader.info

        detected_plates = [
            DetectedPlate(
                track_id=tid, text=agg.text, mean_confidence=agg.mean_confidence,
                observation_count=agg.observation_count, confirmed=agg.confirmed,
            )
            for tid in aggregator.all_track_ids()
            if (agg := aggregator.aggregate(tid)) is not None
        ]

        target_result = None
        if search_mode and lock is not None:
            match_conf = None
            if lock.target_track_id is not None:
                agg = aggregator.aggregate(lock.target_track_id)
                match_conf = agg.mean_confidence if agg else None
            elif lock.confirmed:
                # target was found then lost - report the last known aggregate anyway
                for e in reversed(lock.events):
                    if e.type == "TARGET_VEHICLE_FOUND":
                        agg = aggregator.aggregate(e.track_id)
                        match_conf = agg.mean_confidence if agg else None
                        break
            target_result = TargetVehicleResult(
                found=lock.confirmed,
                track_id=lock.target_track_id,
                plate_text=normalized_target if lock.confirmed else None,
                match_confidence=match_conf,
                first_seen_sec=lock.first_seen_sec,
                last_seen_sec=lock.last_seen_sec,
                visible_duration_sec=lock.visible_duration_sec,
                visible_frame_count=lock.visible_frame_count,
            )

        return AnprResult(
            mode="search" if search_mode else "automatic",
            searched_plate=normalized_target,
            target=target_result,
            detected_plates=detected_plates,
            vehicles_detected=len(vehicle_seen),
            output_video_path=Path(output_path),
            codec_used=writer.open_result.codec_used,
            browser_playable=writer.open_result.browser_playable,
            video_info=video_info,
            metrics=metrics,
            events=sorted(
                [e.__dict__ for e in events.events] + [e.__dict__ for e in (lock.events if lock else [])],
                key=lambda d: d["frame_index"],
            ),
            ocr_status=self.ocr.status.to_dict(),
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
