"""Pure per-track behavioral analytics: loitering, sudden direction change,
abnormal speed, repeated back-and-forth pacing, plus zone/target
correlation into a higher-level TARGET_BEHAVIOR_ALERT.

Zero cv2/ultralytics/torch dependency - operates entirely on
(track_id, point, source-video timestamp) triples the caller already has
from the shared tracker, exactly like core.target_lock and
modules.zone.state. No additional detection model of any kind is run here.

All timing is against the SOURCE VIDEO's own timestamps (the timestamp_sec
the caller passes in, which comes from frame.timestamp_sec = frame_index /
fps), never wall-clock processing time - so results are identical whether
the video is processed at 1x or 20x depending on hardware.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

from backend.config import BehaviorConfig

Point = tuple[float, float]

# Timestamps arrive as repeated float sums/differences (frame_index / fps);
# comparing them against a threshold with plain >= is fragile (e.g.
# 0.3 - 0.2 == 0.09999999999999998 in IEEE754, which is < 0.1 even though
# they're conceptually equal) - all duration/interval threshold checks below
# go through this to absorb that noise instead of missing a real threshold
# crossing by a fraction of a microsecond.
_EPS = 1e-6


def _at_least(value: float, threshold: float) -> bool:
    return value >= threshold - _EPS


@dataclass
class BehaviorEvent:
    type: str  # LOITERING | SUDDEN_DIRECTION_CHANGE | ABNORMAL_SPEED | REPEATED_BACK_AND_FORTH | TARGET_BEHAVIOR_ALERT
    track_id: int
    frame_index: int
    timestamp_sec: float
    data: dict = field(default_factory=dict)


def _distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _angle_diff(a: float, b: float) -> float:
    """Smallest angular difference between two angles in degrees, in [0, 180]."""
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d


@dataclass
class _TrackMotionState:
    # Loitering: an anchor point that only moves once the track strays
    # beyond loitering_radius_px - as long as it stays within radius, the
    # elapsed time since the anchor was set is the current loiter duration.
    loiter_anchor: Point | None = None
    loiter_start_ts: float | None = None
    loiter_emitted: bool = False

    # Direction/speed: a checkpoint that only advances once displacement
    # since the last checkpoint clears min_displacement_px - this is what
    # keeps per-frame tracker/detector jitter from being read as movement.
    checkpoint: tuple[Point, float] | None = None  # (point, timestamp_sec)
    last_angle_deg: float | None = None
    last_speed_px_s: float | None = None

    # Repeated back-and-forth: reversal timestamps within a bounded region.
    pacing_anchor: Point | None = None
    reversal_ts: deque = field(default_factory=deque)

    # Per-behavior-type cooldown bookkeeping (track_id is implicit - this
    # state object already belongs to one track).
    last_event_ts: dict[str, float] = field(default_factory=dict)


class BehaviorMonitor:
    def __init__(self, config: BehaviorConfig | None = None):
        self.cfg = config or BehaviorConfig()
        self._tracks: dict[int, _TrackMotionState] = {}
        self.events: list[BehaviorEvent] = []

    def _cooldown_ok(self, st: _TrackMotionState, behavior_type: str, ts: float) -> bool:
        last = st.last_event_ts.get(behavior_type)
        return last is None or _at_least(ts - last, self.cfg.behavior_cooldown_seconds)

    def _mark(self, st: _TrackMotionState, behavior_type: str, ts: float) -> None:
        st.last_event_ts[behavior_type] = ts

    def update(
        self,
        active_points: dict[int, Point],
        frame_index: int,
        timestamp_sec: float,
        zone_states: dict[int, str] | None = None,
        zone_id: str | None = None,
        target_track_id: int | None = None,
    ) -> list[BehaviorEvent]:
        """Advance one frame for every currently-tracked point. Returns just
        the NEW events produced this call (self.events accumulates all of
        them for the full-run summary)."""
        new_events: list[BehaviorEvent] = []
        for tid, point in active_points.items():
            st = self._tracks.setdefault(tid, _TrackMotionState())
            track_events = self._process_track(tid, st, point, frame_index, timestamp_sec)

            if track_events and (zone_states or target_track_id is not None):
                in_zone = bool(zone_states) and zone_states.get(tid) == "INSIDE"
                is_target = target_track_id is not None and tid == target_track_id
                if (in_zone or is_target) and self._cooldown_ok(st, "TARGET_BEHAVIOR_ALERT", timestamp_sec):
                    self._mark(st, "TARGET_BEHAVIOR_ALERT", timestamp_sec)
                    track_events.append(BehaviorEvent(
                        "TARGET_BEHAVIOR_ALERT", tid, frame_index, timestamp_sec,
                        {"trigger_behavior": track_events[0].type, "zone_id": zone_id if in_zone else None, "is_target": is_target},
                    ))

            new_events.extend(track_events)

        self.events.extend(new_events)
        return new_events

    def _process_track(
        self, tid: int, st: _TrackMotionState, point: Point, frame_index: int, ts: float,
    ) -> list[BehaviorEvent]:
        cfg = self.cfg
        events: list[BehaviorEvent] = []

        # --- LOITERING -------------------------------------------------
        if st.loiter_anchor is None:
            st.loiter_anchor, st.loiter_start_ts, st.loiter_emitted = point, ts, False
        elif _distance(point, st.loiter_anchor) > cfg.loitering_radius_px:
            st.loiter_anchor, st.loiter_start_ts, st.loiter_emitted = point, ts, False
        else:
            duration = ts - st.loiter_start_ts
            if _at_least(duration, cfg.loitering_seconds) and not st.loiter_emitted and self._cooldown_ok(st, "LOITERING", ts):
                st.loiter_emitted = True
                self._mark(st, "LOITERING", ts)
                events.append(BehaviorEvent("LOITERING", tid, frame_index, ts, {
                    "duration_sec": round(duration, 3), "location": st.loiter_anchor,
                }))

        # --- direction / speed segment -----------------------------------
        if st.checkpoint is None:
            st.checkpoint = (point, ts)
        else:
            cp_point, cp_ts = st.checkpoint
            dt = ts - cp_ts
            if _at_least(dt, cfg.sample_interval_sec):
                dx, dy = point[0] - cp_point[0], point[1] - cp_point[1]
                disp = math.hypot(dx, dy)
                if _at_least(disp, cfg.min_displacement_px):
                    angle = math.degrees(math.atan2(dy, dx))
                    speed = disp / dt if dt > 0 else 0.0

                    if st.last_angle_deg is not None:
                        delta = _angle_diff(angle, st.last_angle_deg)

                        if _at_least(delta, cfg.direction_change_degrees) and self._cooldown_ok(st, "SUDDEN_DIRECTION_CHANGE", ts):
                            self._mark(st, "SUDDEN_DIRECTION_CHANGE", ts)
                            events.append(BehaviorEvent("SUDDEN_DIRECTION_CHANGE", tid, frame_index, ts, {
                                "from_angle_deg": round(st.last_angle_deg, 1), "to_angle_deg": round(angle, 1),
                                "delta_deg": round(delta, 1), "location": point,
                            }))

                        if _at_least(delta, cfg.reversal_angle_degrees):
                            if st.pacing_anchor is None or _distance(point, st.pacing_anchor) > cfg.reversal_radius_px:
                                st.pacing_anchor = point
                                st.reversal_ts.clear()
                            st.reversal_ts.append(ts)
                            while st.reversal_ts and ts - st.reversal_ts[0] > cfg.reversal_window_sec:
                                st.reversal_ts.popleft()
                            if len(st.reversal_ts) >= cfg.reversal_count and self._cooldown_ok(st, "REPEATED_BACK_AND_FORTH", ts):
                                self._mark(st, "REPEATED_BACK_AND_FORTH", ts)
                                events.append(BehaviorEvent("REPEATED_BACK_AND_FORTH", tid, frame_index, ts, {
                                    "reversal_count": len(st.reversal_ts), "window_sec": cfg.reversal_window_sec,
                                    "location": point,
                                }))
                                st.reversal_ts.clear()

                    reason = None
                    if _at_least(speed, cfg.speed_threshold_px_per_sec):
                        reason = "high_speed"
                    elif st.last_speed_px_s is not None and _at_least(abs(speed - st.last_speed_px_s), cfg.acceleration_threshold_px_per_sec):
                        reason = "acceleration" if speed > st.last_speed_px_s else "deceleration"
                    if reason and self._cooldown_ok(st, "ABNORMAL_SPEED", ts):
                        self._mark(st, "ABNORMAL_SPEED", ts)
                        events.append(BehaviorEvent("ABNORMAL_SPEED", tid, frame_index, ts, {
                            "reason": reason, "speed_px_per_sec": round(speed, 1),
                            "prev_speed_px_per_sec": round(st.last_speed_px_s, 1) if st.last_speed_px_s is not None else None,
                            "location": point,
                        }))

                    st.last_angle_deg = angle
                    st.last_speed_px_s = speed
                    st.checkpoint = (point, ts)

        return events

    def active_track_ids(self) -> list[int]:
        return list(self._tracks.keys())
