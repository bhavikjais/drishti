"""Pure state machine for target confirmation, occlusion tolerance, and
re-acquisition. Deliberately has zero cv2/ultralytics/torch dependency so it
can be unit-tested in isolation from the real video/CV pipeline.

Shared by every module that locks onto a single tracked object once its
identity is confident enough (person_id by face match, anpr by plate match):
call register_match() for every (track_id, votes, similarity) observation a
frame's sampling step produces, then step_visibility() once per frame with
the set of currently active track ids to learn which track (if any) to draw
the target box for this frame.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum


class TargetLockState(Enum):
    """Purely a derived, read-only view over TargetLock's existing fields --
    added for richer reporting/events without changing any existing
    field/method behavior (test_target_lock.py's assertions are all on the
    existing fields, so they're unaffected by this addition).

    CONFIRMED and REACQUIRED are transition EVENTS (already emitted via
    event_confirmed/event_reacquired), not resting states, so they don't
    appear here -- a lock is never "sitting in" CONFIRMED, it transitions
    through it into TRACKING on the same call.
    """

    SEARCHING = "SEARCHING"  # not yet confirmed, no candidate has any votes yet
    CANDIDATE = "CANDIDATE"  # not yet confirmed, a candidate is accumulating votes
    TRACKING = "TRACKING"  # confirmed, target visible this frame
    TEMPORARILY_LOST = "TEMPORARILY_LOST"  # confirmed, target not visible this frame (occluded or awaiting reacquisition)
    ENDED = "ENDED"  # run finished/cancelled -- terminal


@dataclass
class LockEvent:
    type: str
    track_id: int | None
    frame_index: int
    timestamp_sec: float
    data: dict = field(default_factory=dict)


@dataclass
class TargetLock:
    confirmation_observations: int
    gap_tolerance_frames: int

    # Event type names - overridable so each module can emit its own
    # vocabulary (e.g. TARGET_VEHICLE_FOUND vs TARGET_CONFIRMED) while
    # sharing one state machine implementation.
    event_confirmed: str = "TARGET_CONFIRMED"
    event_reacquired: str = "TARGET_REACQUIRED"
    event_lost: str = "TARGET_LOST"

    confirmed: bool = False
    target_track_id: int | None = None
    first_seen_sec: float | None = None
    last_seen_sec: float | None = None
    visible_frame_count: int = 0
    frames_since_seen: int = 0
    ended: bool = False

    match_counts: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    events: list[LockEvent] = field(default_factory=list)

    @property
    def state(self) -> TargetLockState:
        """Derived resting state -- see TargetLockState's docstring for why
        CONFIRMED/REACQUIRED aren't in this list."""
        if self.ended:
            return TargetLockState.ENDED
        if not self.confirmed:
            has_candidate = any(v > 0 for v in self.match_counts.values())
            return TargetLockState.CANDIDATE if has_candidate else TargetLockState.SEARCHING
        # confirmed: TRACKING only while actually seen THIS frame (frames_since_seen
        # reset to 0 by step_visibility); any gap at all, including the window
        # after a genuine LOST (target_track_id back to None, awaiting
        # reacquisition), reads as TEMPORARILY_LOST.
        if self.target_track_id is not None and self.frames_since_seen == 0:
            return TargetLockState.TRACKING
        return TargetLockState.TEMPORARILY_LOST

    def end(self) -> None:
        """Marks the lock as finished (video ended / job cancelled) -- purely
        a terminal marker for reporting, doesn't affect confirm/track/lost
        logic (which is already done running by the time this is called)."""
        self.ended = True

    def register_match(
        self, track_id: int, frame_index: int, timestamp_sec: float,
        votes: int, similarity: float,
    ) -> None:
        """Record a matching observation for track_id this frame.

        No-op if track_id is already the locked, currently-active target
        (nothing to (re)confirm) and never replaces a target that is still
        actively tracked (target_track_id is not None) with a different
        track's match.
        """
        if self.confirmed and track_id == self.target_track_id:
            return

        self.match_counts[track_id] += 1

        if not self.confirmed:
            if self.match_counts[track_id] >= self.confirmation_observations:
                self.confirmed = True
                self.target_track_id = track_id
                self.first_seen_sec = timestamp_sec
                self.frames_since_seen = 0
                self.events.append(LockEvent(
                    self.event_confirmed, track_id, frame_index, timestamp_sec,
                    {"votes": votes, "similarity": similarity},
                ))
        elif self.target_track_id is None:
            # Confirmed identity, but currently untracked (occlusion) -
            # a strong single-observation match is enough to re-acquire,
            # since it already passed the same threshold/voting bar.
            self.target_track_id = track_id
            self.frames_since_seen = 0
            self.events.append(LockEvent(
                self.event_reacquired, track_id, frame_index, timestamp_sec,
                {"votes": votes, "similarity": similarity},
            ))

    def step_visibility(
        self, active_track_ids: set[int], frame_index: int, timestamp_sec: float,
    ) -> int | None:
        """Advance one frame. Returns the track id to draw this frame, or None."""
        if not self.confirmed or self.target_track_id is None:
            return None

        if self.target_track_id in active_track_ids:
            self.last_seen_sec = timestamp_sec
            self.visible_frame_count += 1
            self.frames_since_seen = 0
            return self.target_track_id

        self.frames_since_seen += 1
        if self.frames_since_seen > self.gap_tolerance_frames:
            self.events.append(LockEvent(
                self.event_lost, self.target_track_id, frame_index, timestamp_sec,
            ))
            self.target_track_id = None
        return None

    @property
    def visible_duration_sec(self) -> float:
        if self.first_seen_sec is None or self.last_seen_sec is None:
            return 0.0
        return round(self.last_seen_sec - self.first_seen_sec, 3)
