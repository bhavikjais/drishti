"""Zone intrusion pipeline: track people/vehicles, test their footpoint
against a user-drawn zone every frame, and annotate the output video with
the zone outline plus ENTRY/EXIT/LONG_DWELL banners.

Zone membership testing runs directly off the shared tracker's per-frame
boxes - no extra AI model, no sampling stride needed, since ray-casting a
point against an n-gon is negligible next to detection/tracking cost.

Also runs zone/forecast.py's intent forecasting alongside the reactive
ZoneMonitor: while ZoneMonitor reports a crossing once it has already
happened, ZoneForecaster extrapolates each track's trajectory forward and
reports PREDICTED_ZONE_CROSSING *before* the track gets there, when its
projected path would cross the boundary within predict_horizon_sec.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from backend.config import TrackerConfig, ZoneConfig
from backend.core.output import (
    GREEN, ORANGE, YELLOW, OutputVideoWriter, draw_banner, draw_polygon,
    draw_predicted_path, draw_target_box, format_timestamp,
)
from backend.core.tracker import ObjectTracker
from backend.core.video import VideoInfo, VideoReader
from backend.modules.zone.forecast import ZoneForecaster
from backend.modules.zone.geometry import Zone, centroid, denormalize_polygon, footpoint
from backend.modules.zone.state import INSIDE, ZoneMonitor

_BANNER_COLOR = {
    "ZONE_ENTRY": ORANGE, "ZONE_EXIT": GREEN, "LONG_DWELL": (0, 0, 200),
    "PREDICTED_ZONE_CROSSING": YELLOW,
}


@dataclass
class TrackSummary:
    track_id: int
    class_name: str
    final_state: str
    entry_count: int
    exit_count: int
    total_dwell_sec: float


@dataclass
class ZoneResult:
    zone_id: str
    output_video_path: Path
    codec_used: str
    browser_playable: bool
    video_info: VideoInfo
    metrics: dict
    events: list[dict]
    tracks_observed: int
    entries: int
    exits: int
    dwell_events: int
    track_summaries: list[TrackSummary]


class ZonePipeline:
    def __init__(self, config: ZoneConfig | None = None, tracker_config: TrackerConfig | None = None):
        self.config = config or ZoneConfig()
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
        zone: Zone,
        output_path: str | Path,
        progress_cb: Callable[[float], None] | None = None,
    ) -> ZoneResult:
        cfg = self.config
        point_fn = footpoint if cfg.point_mode == "footpoint" else centroid

        class_ids = (self.tracker_config.person_class_id, *self.tracker_config.vehicle_class_ids)
        tracker = ObjectTracker(self.tracker_config, class_ids=class_ids)
        monitor = ZoneMonitor(
            zone.zone_id,
            entry_grace_frames=cfg.entry_grace_frames,
            exit_grace_frames=cfg.exit_grace_frames,
            track_absence_grace_frames=cfg.track_absence_grace_frames,
            dwell_threshold_sec=cfg.dwell_threshold_sec,
        )
        forecaster = ZoneForecaster(
            zone.zone_id,
            horizon_sec=cfg.predict_horizon_sec,
            history_frames=cfg.predict_history_frames,
            min_speed_px_per_sec=cfg.predict_min_speed_px_per_sec,
            rewarn_cooldown_sec=cfg.predict_rewarn_cooldown_sec,
        ) if cfg.predict_enabled else None

        norm_polygon = zone.normalized_polygon()
        track_class: dict[int, int] = {}
        active_banners: list[tuple[list[str], tuple[int, int, int], int]] = []  # (lines, color, expire_frame)

        with VideoReader(video_path) as reader:
            writer = OutputVideoWriter(output_path, reader.info)
            polygon_px = denormalize_polygon(norm_polygon, reader.info.width, reader.info.height)
            banner_frames = max(1, int(round(reader.info.fps * cfg.banner_display_sec)))
            progress_stride = max(1, reader.info.frame_count // 100) if reader.info.frame_count else 30

            for frame in reader:
                tracks = tracker.update(frame.image)
                tracks_by_id = {t.track_id: t for t in tracks}
                for tid, t in tracks_by_id.items():
                    track_class[tid] = t.class_id

                points = {tid: point_fn(t.bbox) for tid, t in tracks_by_id.items()}
                n_before = len(monitor.events)
                monitor.update(points, frame.index, frame.timestamp_sec, polygon_px)
                new_events = monitor.events[n_before:]

                new_forecasts = []
                if forecaster is not None:
                    currently_inside = {tid for tid in points if monitor.state_of(tid) == INSIDE}
                    n_before_fc = len(forecaster.events)
                    forecaster.update(points, currently_inside, frame.index, frame.timestamp_sec, polygon_px)
                    new_forecasts = forecaster.events[n_before_fc:]

                draw_polygon(frame.image, polygon_px, label=zone.label or "RESTRICTED ZONE")

                for tid, t in tracks_by_id.items():
                    if monitor.state_of(tid) == INSIDE:
                        cname = self._class_name(t.class_id)
                        draw_target_box(frame.image, t.bbox, label=f"{cname} #{tid}", color=ORANGE, thickness=2)

                for ev in new_events:
                    cname = self._class_name(track_class.get(ev.track_id, -1))
                    if ev.type == "ZONE_ENTRY":
                        lines = ["ZONE ENTRY", f"{cname} #{ev.track_id}", format_timestamp(ev.timestamp_sec)]
                    elif ev.type == "ZONE_EXIT":
                        lines = ["ZONE EXIT", f"{cname} #{ev.track_id}", format_timestamp(ev.timestamp_sec)]
                    else:  # LONG_DWELL
                        lines = ["LONG DWELL", f"{cname} #{ev.track_id}", f"Duration: {ev.data['duration_sec']:.1f} sec"]
                    active_banners.append((lines, _BANNER_COLOR[ev.type], frame.index + banner_frames))

                for ev in new_forecasts:
                    cname = self._class_name(track_class.get(ev.track_id, -1))
                    lines = ["CROSSING PREDICTED", f"{cname} #{ev.track_id}", f"ETA {ev.data['eta_sec']:.1f}s"]
                    active_banners.append((lines, _BANNER_COLOR["PREDICTED_ZONE_CROSSING"], frame.index + banner_frames))
                    if ev.track_id in points:
                        draw_predicted_path(frame.image, points[ev.track_id], tuple(ev.data["predicted_point"]))

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

        forecast_events = forecaster.events if forecaster is not None else []
        events_dicts = sorted(
            [e.__dict__ for e in monitor.events] + [e.__dict__ for e in forecast_events],
            key=lambda d: d["frame_index"],
        )
        entries = sum(1 for e in monitor.events if e.type == "ZONE_ENTRY")
        exits = sum(1 for e in monitor.events if e.type == "ZONE_EXIT")
        dwells = sum(1 for e in monitor.events if e.type == "LONG_DWELL")

        summaries: dict[int, TrackSummary] = {}
        for e in monitor.events:
            s = summaries.setdefault(e.track_id, TrackSummary(
                track_id=e.track_id, class_name=self._class_name(track_class.get(e.track_id, -1)),
                final_state=monitor.state_of(e.track_id), entry_count=0, exit_count=0, total_dwell_sec=0.0,
            ))
            if e.type == "ZONE_ENTRY":
                s.entry_count += 1
            elif e.type == "ZONE_EXIT":
                s.exit_count += 1
                s.total_dwell_sec = round(s.total_dwell_sec + e.data.get("dwell_duration_sec", 0.0), 3)
            s.final_state = monitor.state_of(e.track_id)

        return ZoneResult(
            zone_id=zone.zone_id,
            output_video_path=Path(output_path),
            codec_used=writer.open_result.codec_used,
            browser_playable=writer.open_result.browser_playable,
            video_info=video_info,
            metrics=metrics,
            events=events_dicts,
            tracks_observed=len(track_class),
            entries=entries,
            exits=exits,
            dwell_events=dwells,
            track_summaries=list(summaries.values()),
        )
