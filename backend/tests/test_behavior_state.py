from backend.config import BehaviorConfig
from backend.modules.behavior.state import BehaviorMonitor


def types_of(events):
    return [e.type for e in events]


def test_stationary_track_triggers_loitering():
    cfg = BehaviorConfig(loitering_seconds=2.0, loitering_radius_px=20.0, behavior_cooldown_seconds=100.0)
    m = BehaviorMonitor(cfg)
    for i, t in enumerate([0.0, 0.5, 1.0, 1.5, 1.9]):
        events = m.update({1: (100.0, 100.0)}, i, t)
        assert types_of(events) == []  # not yet at threshold
    events = m.update({1: (101.0, 100.0)}, 5, 2.0)  # tiny jitter, still within radius
    assert types_of(events) == ["LOITERING"]
    assert events[0].data["duration_sec"] >= 2.0
    assert events[0].track_id == 1


def test_moving_track_does_not_falsely_loiter():
    cfg = BehaviorConfig(loitering_seconds=2.0, loitering_radius_px=20.0)
    m = BehaviorMonitor(cfg)
    all_events = []
    x = 0.0
    for i, t in enumerate([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]):
        x += 30.0  # steadily walks away, always beyond loitering_radius_px=20 from the anchor
        all_events += m.update({1: (x, 0.0)}, i, t)
    assert "LOITERING" not in types_of(all_events)


def test_genuine_direction_change_is_detected():
    cfg = BehaviorConfig(direction_change_degrees=60.0, min_displacement_px=5.0, sample_interval_sec=0.1, behavior_cooldown_seconds=100.0)
    m = BehaviorMonitor(cfg)
    m.update({1: (0.0, 0.0)}, 0, 0.0)      # initial checkpoint
    m.update({1: (20.0, 0.0)}, 1, 0.1)     # moving right, first segment (no prior angle to compare)
    events = m.update({1: (40.0, 0.0)}, 2, 0.2)  # still moving right - no change
    assert types_of(events) == []
    events = m.update({1: (40.0, 20.0)}, 3, 0.3)  # abrupt 90-degree turn
    assert types_of(events) == ["SUDDEN_DIRECTION_CHANGE"]
    assert events[0].data["delta_deg"] == 90.0


def test_tiny_noisy_movements_are_ignored():
    cfg = BehaviorConfig(direction_change_degrees=60.0, min_displacement_px=5.0, sample_interval_sec=0.1)
    m = BehaviorMonitor(cfg)
    all_events = []
    # sub-pixel-threshold jitter around the same spot, alternating direction each frame
    points = [(100.0, 100.0), (102.0, 100.0), (99.0, 101.0), (101.0, 99.0), (100.0, 102.0)]
    for i, (pt, t) in enumerate(zip(points, [0.0, 0.1, 0.2, 0.3, 0.4])):
        all_events += m.update({1: pt}, i, t)
    assert "SUDDEN_DIRECTION_CHANGE" not in types_of(all_events)


def test_abnormal_speed_is_detected():
    cfg = BehaviorConfig(speed_threshold_px_per_sec=100.0, min_displacement_px=5.0, sample_interval_sec=0.1, behavior_cooldown_seconds=100.0)
    m = BehaviorMonitor(cfg)
    m.update({1: (0.0, 0.0)}, 0, 0.0)
    # 500px in 0.1s = 5000 px/s, far above the 100 px/s threshold
    events = m.update({1: (500.0, 0.0)}, 1, 0.1)
    assert "ABNORMAL_SPEED" in types_of(events)
    ev = next(e for e in events if e.type == "ABNORMAL_SPEED")
    assert ev.data["reason"] == "high_speed"
    assert ev.data["speed_px_per_sec"] == 5000.0


def test_normal_speed_does_not_trigger():
    cfg = BehaviorConfig(speed_threshold_px_per_sec=1000.0, acceleration_threshold_px_per_sec=1000.0, min_displacement_px=5.0, sample_interval_sec=0.1)
    m = BehaviorMonitor(cfg)
    all_events = []
    x = 0.0
    for i, t in enumerate([0.0, 0.1, 0.2, 0.3, 0.4]):
        x += 10.0  # 100 px/s - well under the 1000 px/s threshold
        all_events += m.update({1: (x, 0.0)}, i, t)
    assert "ABNORMAL_SPEED" not in types_of(all_events)


def test_repeated_reversals_trigger_back_and_forth_after_threshold_count():
    cfg = BehaviorConfig(
        reversal_angle_degrees=120.0, reversal_count=3, reversal_window_sec=20.0, reversal_radius_px=100.0,
        min_displacement_px=5.0, sample_interval_sec=0.1, direction_change_degrees=60.0, behavior_cooldown_seconds=5.0,
    )
    m = BehaviorMonitor(cfg)
    points = [(0.0, 0.0), (20.0, 0.0), (0.0, 0.0), (20.0, 0.0), (0.0, 0.0)]
    all_events = []
    for i, (pt, t) in enumerate(zip(points, [0.0, 0.1, 0.2, 0.3, 0.4])):
        all_events += m.update({1: pt}, i, t)
    back_and_forth = [e for e in all_events if e.type == "REPEATED_BACK_AND_FORTH"]
    assert len(back_and_forth) == 1  # fires once, exactly when the 3rd reversal lands
    assert back_and_forth[0].data["reversal_count"] == 3
    assert back_and_forth[0].timestamp_sec == 0.4


def test_two_reversals_are_not_enough():
    cfg = BehaviorConfig(reversal_angle_degrees=120.0, reversal_count=3, min_displacement_px=5.0, sample_interval_sec=0.1)
    m = BehaviorMonitor(cfg)
    points = [(0.0, 0.0), (20.0, 0.0), (0.0, 0.0)]  # only 1 reversal
    all_events = []
    for i, (pt, t) in enumerate(zip(points, [0.0, 0.1, 0.2])):
        all_events += m.update({1: pt}, i, t)
    assert "REPEATED_BACK_AND_FORTH" not in types_of(all_events)


def test_event_cooldown_suppresses_immediate_repeat():
    cfg = BehaviorConfig(loitering_seconds=0.1, loitering_radius_px=10.0, behavior_cooldown_seconds=0.5)
    m = BehaviorMonitor(cfg)
    all_events = []
    all_events += m.update({1: (0.0, 0.0)}, 0, 0.0)
    all_events += m.update({1: (0.0, 0.0)}, 1, 0.1)  # duration 0.1s -> fires episode 1
    all_events += m.update({1: (1000.0, 1000.0)}, 2, 0.15)  # leaves - new anchor, episode ends
    all_events += m.update({1: (1000.0, 1000.0)}, 3, 0.25)  # duration 0.1s again, but within cooldown -> suppressed
    all_events += m.update({1: (1000.0, 1000.0)}, 4, 0.35)  # still within cooldown -> suppressed
    all_events += m.update({1: (1000.0, 1000.0)}, 5, 0.65)  # cooldown (0.5s since t=0.1) has now elapsed -> fires

    loiter_events = [e for e in all_events if e.type == "LOITERING"]
    assert len(loiter_events) == 2
    assert loiter_events[0].timestamp_sec == 0.1
    assert loiter_events[1].timestamp_sec == 0.65


def test_multiple_tracks_have_independent_state():
    cfg = BehaviorConfig(loitering_seconds=0.2, loitering_radius_px=10.0)
    m = BehaviorMonitor(cfg)
    all_events = []
    # track 1 stays put (will loiter), track 2 keeps moving away (won't)
    x2 = 0.0
    for i, t in enumerate([0.0, 0.1, 0.2, 0.3]):
        x2 += 50.0
        all_events += m.update({1: (0.0, 0.0), 2: (x2, 0.0)}, i, t)
    track1_events = [e for e in all_events if e.track_id == 1]
    track2_events = [e for e in all_events if e.track_id == 2]
    assert any(e.type == "LOITERING" for e in track1_events)
    assert not any(e.type == "LOITERING" for e in track2_events)


def test_zone_and_behavior_correlation_produces_target_behavior_alert():
    cfg = BehaviorConfig(loitering_seconds=0.1, loitering_radius_px=10.0, behavior_cooldown_seconds=100.0)
    m = BehaviorMonitor(cfg)
    m.update({1: (0.0, 0.0)}, 0, 0.0, zone_states={1: "OUTSIDE"}, zone_id="zone-1")
    events = m.update({1: (0.0, 0.0)}, 1, 0.1, zone_states={1: "INSIDE"}, zone_id="zone-1")
    assert "LOITERING" in types_of(events)
    assert "TARGET_BEHAVIOR_ALERT" in types_of(events)
    alert = next(e for e in events if e.type == "TARGET_BEHAVIOR_ALERT")
    assert alert.data["trigger_behavior"] == "LOITERING"
    assert alert.data["zone_id"] == "zone-1"
    assert alert.data["is_target"] is False


def test_zone_outside_does_not_produce_target_behavior_alert():
    cfg = BehaviorConfig(loitering_seconds=0.1, loitering_radius_px=10.0)
    m = BehaviorMonitor(cfg)
    m.update({1: (0.0, 0.0)}, 0, 0.0, zone_states={1: "OUTSIDE"})
    events = m.update({1: (0.0, 0.0)}, 1, 0.1, zone_states={1: "OUTSIDE"})
    assert "LOITERING" in types_of(events)
    assert "TARGET_BEHAVIOR_ALERT" not in types_of(events)


def test_target_track_correlation_produces_target_behavior_alert():
    cfg = BehaviorConfig(loitering_seconds=0.1, loitering_radius_px=10.0, behavior_cooldown_seconds=100.0)
    m = BehaviorMonitor(cfg)
    m.update({1: (0.0, 0.0), 2: (0.0, 0.0)}, 0, 0.0, target_track_id=1)
    events = m.update({1: (0.0, 0.0), 2: (0.0, 0.0)}, 1, 0.1, target_track_id=1)
    # both tracks loiter identically, but only track 1 (the target) escalates
    target_alerts = [e for e in events if e.type == "TARGET_BEHAVIOR_ALERT"]
    assert len(target_alerts) == 1
    assert target_alerts[0].track_id == 1
    assert target_alerts[0].data["is_target"] is True
