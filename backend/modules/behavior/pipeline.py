"""Behavioral analytics pipeline: loitering, sudden direction change,
abnormal speed, and repeated back-and-forth pacing, computed purely from the
shared tracker's per-frame output - no extra detection model of any kind.

Reuses (does not reimplement) modules.zone.state.ZoneMonitor when a zone is
supplied, for genuine zone+behavior correlation on the SAME tracker pass
(zero extra AI cost - it's just cheap geometry on boxes already computed).
An optional target_track_id (e.g. carried over from a prior Person-ID/ANPR
run's locked track) enables target+behavior correlation the same way. Both
are optional; with neither, this still detects and annotates the 4 base
behaviors on their own.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2

from backend.config import BehaviorConfig, TrackerConfig
from backend.core.output import (
    MAGENTA, ORANGE, RED, OutputVideoWriter, draw_banner, draw_polygon,
    draw_target_box, format_timestamp,
)
from backend.core.tracker import ObjectTracker
from backend.core.video import VideoInfo, VideoReader
from backend.modules.behavior.state import BehaviorMonitor
from backend.modules.zone.geometry import Zone, centroid, denormalize_polygon, footpoint
from backend.modules.zone.state import INSIDE, ZoneMonitor

_BANNER_COLOR = {
    "LOITERING": ORANGE,
    "SUDDEN_DIRECTION_CHANGE": ORANGE,
    "ABNORMAL_SPEED": ORANGE,
    "REPEATED_BACK_AND_FORTH": ORANGE,
    "TARGET_BEHAVIOR_ALERT": RED,
}
_LABEL_TEXT = {
    "LOITERING": "LOITERING",
    "SUDDEN_DIRECTION_CHANGE": "SUDDEN DIRECTION CHANGE",
    "ABNORMAL_SPEED": "ABNORMAL SPEED",
    "REPEATED_BACK_AND_FORTH": "REPEATED PACING",
}


@dataclass
class BehaviorResult:
    output_video_path: Path
    codec_used: str
    browser_playable: bool
    video_info: VideoInfo
    metrics: dict
    events: list[dict]
    tracks_observed: int
    event_counts: dict[str, int]
    evidence_dir: Path | None


class BehaviorPipeline:
    def __init__(self, config: BehaviorConfig | None = None, tracker_config: TrackerConfig | None = None):
        self.config = config or BehaviorConfig()
        self.tracker_config = tracker_config or TrackerConfig()

    def _class_name(self, class_id: int) -> str:
        if class_id == self.tracker_config.person_class_id:
            return "PERSON"
        if class_id in self.tracker_config.vehicle_class_ids:
            return "VEHICLE"
        return "OBJECT"

    def run(
        self,
        video_path: str | Path,
        output_path: str | Path,
        zone: Zone | None = None,
        target_track_id: int | None = None,
        evidence_dir: str | Path | None = None,
        progress_cb: Callable[[float], None] | None = None,
    ) -> BehaviorResult:
        cfg = self.config
        class_ids = (self.tracker_config.person_class_id, *self.tracker_config.vehicle_class_ids)
        tracker = ObjectTracker(self.tracker_config, class_ids=class_ids)
        monitor = BehaviorMonitor(cfg)

        zone_monitor: ZoneMonitor | None = None
        polygon_px: list[tuple[int, int]] | None = None
        if zone is not None:
            zone_monitor = ZoneMonitor(zone.zone_id)  # default grace/dwell config; only used for INSIDE/OUTSIDE state here

        if evidence_dir is not None:
            evidence_dir = Path(evidence_dir)
            if evidence_dir.exists():
                shutil.rmtree(evidence_dir)
            evidence_dir.mkdir(parents=True, exist_ok=True)

        track_class: dict[int, int] = {}
        active_banners: list[tuple[list[str], tuple[int, int, int], int]] = []
        alert_active_until: dict[int, int] = {}  # track_id -> frame_index the alert box stays drawn until

        with VideoReader(video_path) as reader:
            writer = OutputVideoWriter(output_path, reader.info)
            if zone is not None:
                polygon_px = denormalize_polygon(zone.normalized_polygon(), reader.info.width, reader.info.height)
            alert_frames = max(1, int(round(reader.info.fps * cfg.alert_display_sec)))
            progress_stride = max(1, reader.info.frame_count // 100) if reader.info.frame_count else 30

            for frame in reader:
                tracks = tracker.update(frame.image)
                tracks_by_id = {t.track_id: t for t in tracks}
                for tid, t in tracks_by_id.items():
                    track_class[tid] = t.class_id

                zone_states = None
                if zone_monitor is not None and polygon_px is not None:
                    footpoints = {tid: footpoint(t.bbox) for tid, t in tracks_by_id.items()}
                    zone_monitor.update(footpoints, frame.index, frame.timestamp_sec, polygon_px)
                    zone_states = {tid: zone_monitor.state_of(tid) for tid in tracks_by_id}

                centroids = {tid: centroid(t.bbox) for tid, t in tracks_by_id.items()}
                new_events = monitor.update(
                    centroids, frame.index, frame.timestamp_sec,
                    zone_states=zone_states, zone_id=(zone.zone_id if zone else None),
                    target_track_id=target_track_id,
                )

                if zone is not None and polygon_px is not None:
                    draw_polygon(frame.image, polygon_px, label=zone.label or "RESTRICTED ZONE")

                for ev in new_events:
                    alert_active_until[ev.track_id] = frame.index + alert_frames
                    cname = self._class_name(track_class.get(ev.track_id, -1))
                    if ev.type == "TARGET_BEHAVIOR_ALERT":
                        lines = ["TARGET BEHAVIOR ALERT", f"{cname} #{ev.track_id}", ev.data["trigger_behavior"]]
                    else:
                        lines = ["BEHAVIOR ALERT", f"{_LABEL_TEXT[ev.type]} - {cname} #{ev.track_id}", format_timestamp(ev.timestamp_sec)]
                    active_banners.append((lines, _BANNER_COLOR[ev.type], frame.index + alert_frames))

                    if evidence_dir is not None and ev.track_id in tracks_by_id:
                        bbox = tracks_by_id[ev.track_id].bbox
                        x1, y1, x2, y2 = (max(0, v) for v in bbox)
                        crop = frame.image[y1:y2, x1:x2]
                        if crop.size:
                            fname = f"{ev.track_id}_{ev.type}_{ev.frame_index}.jpg"
                            cv2.imwrite(str(evidence_dir / fname), crop)

                for tid, t in tracks_by_id.items():
                    until = alert_active_until.get(tid)
                    if until is not None and frame.index < until:
                        cname = self._class_name(t.class_id)
                        draw_target_box(frame.image, t.bbox, label=f"{cname} #{tid}", color=MAGENTA, thickness=2)

                active_banners = [b for b in active_banners if b[2] > frame.index]
                for slot, (lines, color, _expire) in enumerate(active_banners):
                    draw_banner(frame.image, lines, color, slot=slot)

                writer.write(frame.image)
                if progress_cb is not None and (frame.index % progress_stride == 0) and reader.info.frame_count:
                    progress_cb(min(1.0, frame.index / reader.info.frame_count))

            writer.close()
            reader.metrics.frames_written = writer.frames_written
            metrics = reader.metrics.as_dict()
            video_info = reader.info

        if progress_cb is not None:
            progress_cb(1.0)

        event_counts: dict[str, int] = {}
        for e in monitor.events:
            event_counts[e.type] = event_counts.get(e.type, 0) + 1

        return BehaviorResult(
            output_video_path=Path(output_path),
            codec_used=writer.open_result.codec_used,
            browser_playable=writer.open_result.browser_playable,
            video_info=video_info,
            metrics=metrics,
            events=[e.__dict__ for e in monitor.events],
            tracks_observed=len(track_class),
            event_counts=event_counts,
            evidence_dir=evidence_dir,
        )
