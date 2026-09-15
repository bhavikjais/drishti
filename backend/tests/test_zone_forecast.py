from backend.modules.zone.forecast import ZoneForecaster

ZONE = [(0, 0), (10, 0), (10, 10), (0, 10)]


def make_forecaster(horizon=5.0, history=5, min_speed=1.0, cooldown=8.0):
    return ZoneForecaster(
        "zone-1", horizon_sec=horizon, history_frames=history,
        min_speed_px_per_sec=min_speed, rewarn_cooldown_sec=cooldown,
    )


def test_no_prediction_with_fewer_than_two_samples():
    fc = make_forecaster()
    fc.update({1: (20, 5)}, set(), 0, 0.0, ZONE)
    assert fc.events == []


def test_approaching_track_predicts_crossing_within_horizon():
    fc = make_forecaster(horizon=5.0)
    fc.update({1: (20, 5)}, set(), 0, 0.0, ZONE)
    fc.update({1: (15, 5)}, set(), 1, 1.0, ZONE)  # moving at -5 px/sec toward the zone's right edge (x=10)

    assert len(fc.events) == 1
    ev = fc.events[0]
    assert ev.type == "PREDICTED_ZONE_CROSSING"
    assert ev.track_id == 1
    assert ev.zone_id == "zone-1"
    assert ev.data["eta_sec"] == 1.0  # at x=15 moving -5px/s, hits x=10 in exactly 1s
    assert ev.data["predicted_point"] == [10, 5]


def test_stationary_track_never_predicted():
    fc = make_forecaster(min_speed=1.0)
    fc.update({1: (20, 5)}, set(), 0, 0.0, ZONE)
    fc.update({1: (20, 5)}, set(), 1, 1.0, ZONE)
    fc.update({1: (20, 5)}, set(), 2, 2.0, ZONE)
    assert fc.events == []


def test_track_moving_away_is_never_predicted():
    fc = make_forecaster()
    fc.update({1: (15, 5)}, set(), 0, 0.0, ZONE)
    fc.update({1: (20, 5)}, set(), 1, 1.0, ZONE)  # moving away at +5 px/sec
    fc.update({1: (25, 5)}, set(), 2, 2.0, ZONE)
    assert fc.events == []


def test_eta_beyond_horizon_is_not_reported():
    fc = make_forecaster(horizon=0.5)  # crossing is 1s out, horizon only covers 0.5s
    fc.update({1: (20, 5)}, set(), 0, 0.0, ZONE)
    fc.update({1: (15, 5)}, set(), 1, 1.0, ZONE)
    assert fc.events == []


def test_track_already_inside_is_skipped_and_resets_warned_state():
    fc = make_forecaster()
    fc.update({1: (20, 5)}, set(), 0, 0.0, ZONE)
    fc.update({1: (15, 5)}, set(), 1, 1.0, ZONE)
    assert len(fc.events) == 1  # warned once while approaching

    # now ZoneMonitor considers it actually INSIDE - forecaster should back off
    fc.update({1: (9, 5)}, {1}, 2, 2.0, ZONE)
    assert len(fc.events) == 1  # no new prediction fired while inside


def test_does_not_repeat_warning_within_cooldown():
    fc = make_forecaster(horizon=20.0, cooldown=5.0)
    fc.update({1: (100, 5)}, set(), 0, 0.0, ZONE)
    fc.update({1: (95, 5)}, set(), 1, 1.0, ZONE)  # first warning fires here
    assert len(fc.events) == 1

    fc.update({1: (90, 5)}, set(), 2, 2.0, ZONE)  # still approaching, well within cooldown
    fc.update({1: (85, 5)}, set(), 3, 3.0, ZONE)
    assert len(fc.events) == 1  # no duplicate warning yet


def test_rewarns_after_cooldown_elapses():
    fc = make_forecaster(horizon=20.0, cooldown=1.5)
    fc.update({1: (100, 5)}, set(), 0, 0.0, ZONE)
    fc.update({1: (95, 5)}, set(), 1, 1.0, ZONE)  # first warning (last_warning_ts=1.0)
    assert len(fc.events) == 1

    fc.update({1: (90, 5)}, set(), 2, 2.0, ZONE)  # elapsed 1.0s since warning, still < 1.5s cooldown
    fc.update({1: (85, 5)}, set(), 3, 3.0, ZONE)  # elapsed 2.0s since warning, >= 1.5s cooldown
    assert len(fc.events) == 2


def test_independent_tracks_do_not_interfere():
    fc = make_forecaster()
    fc.update({1: (20, 5), 2: (5, 20)}, set(), 0, 0.0, ZONE)
    fc.update({1: (15, 5), 2: (5, 25)}, set(), 1, 1.0, ZONE)  # track 1 approaches, track 2 moves away

    types_by_track = {(e.track_id, e.type) for e in fc.events}
    assert (1, "PREDICTED_ZONE_CROSSING") in types_by_track
    assert not any(tid == 2 for tid, _ in types_by_track)


def test_track_dropped_from_history_when_no_longer_seen():
    fc = make_forecaster()
    fc.update({1: (20, 5)}, set(), 0, 0.0, ZONE)
    fc.update({}, set(), 1, 1.0, ZONE)  # track 1 gone
    assert fc._history == {}
