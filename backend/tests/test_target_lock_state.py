"""Tests for TargetLockState -- the new derived-state property added to
TargetLock. Purely additive: does not touch any existing field/method, so
these are separate from test_target_lock.py (which already covers
confirm/lost/reacquire mechanics and stays green untouched)."""
from backend.core.target_lock import TargetLock, TargetLockState


def test_searching_before_any_votes():
    lock = TargetLock(confirmation_observations=2, gap_tolerance_frames=5)
    assert lock.state == TargetLockState.SEARCHING


def test_candidate_once_votes_start_accumulating():
    lock = TargetLock(confirmation_observations=3, gap_tolerance_frames=5)
    lock.register_match(1, 0, 0.0, votes=1, similarity=0.5)
    assert lock.state == TargetLockState.CANDIDATE


def test_tracking_once_confirmed_and_visible():
    lock = TargetLock(confirmation_observations=1, gap_tolerance_frames=5)
    lock.register_match(1, 0, 0.0, votes=1, similarity=0.9)
    lock.step_visibility({1}, 0, 0.0)
    assert lock.state == TargetLockState.TRACKING


def test_temporarily_lost_within_gap_tolerance():
    lock = TargetLock(confirmation_observations=1, gap_tolerance_frames=5)
    lock.register_match(1, 0, 0.0, votes=1, similarity=0.9)
    lock.step_visibility({1}, 0, 0.0)
    lock.step_visibility(set(), 1, 0.1)  # target not in this frame's tracks
    assert lock.state == TargetLockState.TEMPORARILY_LOST
    assert lock.target_track_id == 1  # identity preserved, not reset


def test_still_temporarily_lost_after_genuine_lost_event():
    lock = TargetLock(confirmation_observations=1, gap_tolerance_frames=2)
    lock.register_match(1, 0, 0.0, votes=1, similarity=0.9)
    lock.step_visibility({1}, 0, 0.0)
    for i in range(1, 5):
        lock.step_visibility(set(), i, float(i))
    assert lock.target_track_id is None  # genuinely declared lost
    assert lock.state == TargetLockState.TEMPORARILY_LOST  # still awaiting reacquisition, per spec


def test_ended_is_terminal():
    lock = TargetLock(confirmation_observations=1, gap_tolerance_frames=5)
    lock.end()
    assert lock.state == TargetLockState.ENDED
    # even a confirmed/tracking lock reports ENDED once ended
    lock2 = TargetLock(confirmation_observations=1, gap_tolerance_frames=5)
    lock2.register_match(1, 0, 0.0, votes=1, similarity=0.9)
    lock2.step_visibility({1}, 0, 0.0)
    lock2.end()
    assert lock2.state == TargetLockState.ENDED
