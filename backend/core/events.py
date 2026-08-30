"""Deduplicated event stream shared by all module pipelines.

The point of EventBus is to stop pipelines from emitting hundreds of
near-duplicate events for the same object. Emission is keyed by
(event_type, track_id); a repeat of the same key is dropped unless the
configured cooldown has elapsed, or the emitter explicitly marks a state
transition (e.g. ENTER -> DWELL -> EXIT) via `state`.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Event:
    type: str
    track_id: int | None
    frame_index: int
    timestamp_sec: float
    data: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "type": self.type,
            "track_id": self.track_id,
            "frame_index": self.frame_index,
            "timestamp_sec": round(self.timestamp_sec, 3),
            **self.data,
        }


class EventBus:
    def __init__(self):
        self._events: list[Event] = []
        # (event_type, track_id) -> (last_emit_timestamp_sec, last_state)
        self._last: dict[tuple[str, int | None], tuple[float, str | None]] = {}

    def emit(
        self,
        event_type: str,
        track_id: int | None,
        frame_index: int,
        timestamp_sec: float,
        cooldown_sec: float = 0.0,
        state: str | None = None,
        **data,
    ) -> Event | None:
        """Emit an event unless it's a duplicate within the cooldown window.

        A change in `state` (e.g. moving from ENTER to DWELL) always bypasses
        the cooldown, since that's a real transition, not a repeat.
        """
        key = (event_type, track_id)
        prev = self._last.get(key)
        if prev is not None:
            prev_ts, prev_state = prev
            same_state = state is None or state == prev_state
            if same_state and (timestamp_sec - prev_ts) < cooldown_sec:
                return None

        event = Event(
            type=event_type,
            track_id=track_id,
            frame_index=frame_index,
            timestamp_sec=timestamp_sec,
            data=data,
        )
        self._events.append(event)
        self._last[key] = (timestamp_sec, state)
        return event

    @property
    def events(self) -> list[Event]:
        return list(self._events)

    def as_dicts(self) -> list[dict]:
        return [e.as_dict() for e in self._events]
