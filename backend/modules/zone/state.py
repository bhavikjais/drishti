"""Per-track, per-zone state machine: OUTSIDE/INSIDE/UNKNOWN, entry/exit
debounce, dwell tracking. Deliberately has zero cv2/ultralytics/torch
dependency (pure Python) so it's unit-testable without real video or CV
models - same philosophy as core.target_lock.

One ZoneMonitor instance owns exactly one zone's state for every track
independently (a dict keyed by track_id), so multiple simultaneous objects
never share or clobber each other's state, and multiple zones are just
multiple ZoneMonitor instances (each carries its own zone_id).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.modules.zone.geometry import point_in_polygon

UNKNOWN, OUTSIDE, INSIDE = "UNKNOWN", "OUTSIDE", "INSIDE"


@dataclass
class ZoneEvent:
    type: str  # ZONE_ENTRY | ZONE_EXIT | LONG_DWELL
    zone_id: str
    track_id: int
    frame_index: int
    timestamp_sec: float
    data: dict = field(default_factory=dict)


@dataclass
class _TrackState:
    state: str = UNKNOWN
    pending_inside: int = 0
    pending_outside: int = 0
    absence_count: int = 0
    entry_ts: float | None = None
    dwell_emitted: bool = False


class ZoneMonitor:
    def __init__(
        self,
        zone_id: str,
        entry_grace_frames: int = 3,
        exit_grace_frames: int = 15,
        track_absence_grace_frames: int = 45,
        dwell_threshold_sec: float = 15.0,
    ):
        self.zone_id = zone_id
        self.entry_grace_frames = max(1, entry_grace_frames)
        self.exit_grace_frames = max(1, exit_grace_frames)
        self.track_absence_grace_frames = max(1, track_absence_grace_frames)
        self.dwell_threshold_sec = dwell_threshold_sec
        self._tracks: dict[int, _TrackState] = {}
        self.events: list[ZoneEvent] = []

    def state_of(self, track_id: int) -> str:
        st = self._tracks.get(track_id)
        return st.state if st else UNKNOWN

    def update(
        self,
        active_points: dict[int, tuple[float, float]],
        frame_index: int,
        timestamp_sec: float,
        polygon: list[tuple[float, float]],
    ) -> None:
        """Advance one frame. active_points maps track_id -> the point
        (footpoint/centroid, in the SAME coordinate space as polygon) to test
        for every track currently detected this frame. Tracks known from a
        previous frame but absent from active_points are treated as a
        detection gap, not an instant exit.
        """
        seen = set(active_points.keys())

        for tid, st in list(self._tracks.items()):
            if tid in seen:
                continue
            st.absence_count += 1
            if st.state == INSIDE and st.absence_count > self.track_absence_grace_frames:
                self._commit_exit(tid, st, frame_index, timestamp_sec)
            elif st.absence_count > self.track_absence_grace_frames * 4:
                del self._tracks[tid]  # bound memory for long-gone tracks

        for tid, point in active_points.items():
            st = self._tracks.setdefault(tid, _TrackState())
            st.absence_count = 0
            inside = point_in_polygon(point, polygon)

            if st.state != INSIDE:
                if inside:
                    st.pending_inside += 1
                    st.pending_outside = 0
                    if st.pending_inside >= self.entry_grace_frames:
                        self._commit_entry(tid, st, frame_index, timestamp_sec)
                else:
                    st.pending_inside = 0
                    if st.state == UNKNOWN:
                        st.state = OUTSIDE  # safe immediate default, no event
            else:
                if inside:
                    st.pending_outside = 0
                else:
                    st.pending_outside += 1
                    if st.pending_outside >= self.exit_grace_frames:
                        self._commit_exit(tid, st, frame_index, timestamp_sec)
                        continue
                if st.state == INSIDE and not st.dwell_emitted and st.entry_ts is not None:
                    dwell = timestamp_sec - st.entry_ts
                    if dwell >= self.dwell_threshold_sec:
                        st.dwell_emitted = True
                        self.events.append(ZoneEvent(
                            "LONG_DWELL", self.zone_id, tid, frame_index, timestamp_sec,
                            {"duration_sec": round(dwell, 3)},
                        ))

    def _commit_entry(self, tid: int, st: _TrackState, frame_index: int, ts: float) -> None:
        st.state = INSIDE
        st.entry_ts = ts
        st.dwell_emitted = False
        st.pending_inside = 0
        self.events.append(ZoneEvent("ZONE_ENTRY", self.zone_id, tid, frame_index, ts, {}))

    def _commit_exit(self, tid: int, st: _TrackState, frame_index: int, ts: float) -> None:
        dwell = (ts - st.entry_ts) if st.entry_ts is not None else 0.0
        st.state = OUTSIDE
        st.pending_outside = 0
        st.absence_count = 0
        st.entry_ts = None
        self.events.append(ZoneEvent(
            "ZONE_EXIT", self.zone_id, tid, frame_index, ts,
            {"dwell_duration_sec": round(dwell, 3)},
        ))
