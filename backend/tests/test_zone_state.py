from backend.modules.zone.state import INSIDE, OUTSIDE, UNKNOWN, ZoneMonitor

ZONE = [(0, 0), (10, 0), (10, 10), (0, 10)]
OUTSIDE_PT = (20, 20)
INSIDE_PT = (5, 5)


def make_monitor(entry_grace=3, exit_grace=5, absence_grace=10, dwell_threshold=15.0):
    return ZoneMonitor(
        "zone-1", entry_grace_frames=entry_grace, exit_grace_frames=exit_grace,
        track_absence_grace_frames=absence_grace, dwell_threshold_sec=dwell_threshold,
    )


def test_initial_state_is_unknown():
    m = make_monitor()
    assert m.state_of(1) == UNKNOWN


def test_outside_to_inside_transition_fires_zone_entry():
    m = make_monitor(entry_grace=3)
    for i in range(3):
        m.update({1: INSIDE_PT}, i, i / 30, ZONE)
    assert m.state_of(1) == INSIDE
    assert [e.type for e in m.events] == ["ZONE_ENTRY"]
    assert m.events[0].track_id == 1
    assert m.events[0].zone_id == "zone-1"


def test_entry_requires_consecutive_grace_frames_not_just_one():
    m = make_monitor(entry_grace=3)
    m.update({1: INSIDE_PT}, 0, 0.0, ZONE)
    m.update({1: INSIDE_PT}, 1, 0.03, ZONE)
    assert m.state_of(1) == UNKNOWN  # only 2/3 consecutive frames so far
    assert m.events == []


def test_inside_to_outside_transition_fires_zone_exit():
    m = make_monitor(entry_grace=2, exit_grace=2)
    m.update({1: INSIDE_PT}, 0, 0.0, ZONE)
    m.update({1: INSIDE_PT}, 1, 0.1, ZONE)
    assert m.state_of(1) == INSIDE

    m.update({1: OUTSIDE_PT}, 2, 0.2, ZONE)
    m.update({1: OUTSIDE_PT}, 3, 0.3, ZONE)
    assert m.state_of(1) == OUTSIDE
    types = [e.type for e in m.events]
    assert types == ["ZONE_ENTRY", "ZONE_EXIT"]
    assert m.events[1].data["dwell_duration_sec"] == round(0.3 - 0.1, 3)


def test_short_detection_gap_does_not_trigger_exit():
    m = make_monitor(entry_grace=2, absence_grace=5)
    m.update({1: INSIDE_PT}, 0, 0.0, ZONE)
    m.update({1: INSIDE_PT}, 1, 0.1, ZONE)
    assert m.state_of(1) == INSIDE

    # track missing (occlusion) for 3 frames, below absence_grace=5
    for i in range(2, 5):
        m.update({}, i, i / 30, ZONE)
    assert m.state_of(1) == INSIDE  # still inside, no premature exit
    assert [e.type for e in m.events] == ["ZONE_ENTRY"]

    # track reappears inside - dwell clock should not have reset
    m.update({1: INSIDE_PT}, 5, 5 / 30, ZONE)
    assert m.state_of(1) == INSIDE


def test_absence_beyond_grace_period_triggers_exit():
    m = make_monitor(entry_grace=1, absence_grace=3)
    m.update({1: INSIDE_PT}, 0, 0.0, ZONE)
    assert m.state_of(1) == INSIDE

    for i in range(1, 6):  # 5 missing frames > absence_grace=3
        m.update({}, i, i / 10, ZONE)
    assert m.state_of(1) == OUTSIDE
    assert [e.type for e in m.events] == ["ZONE_ENTRY", "ZONE_EXIT"]


def test_long_dwell_fires_once_when_threshold_crossed():
    m = make_monitor(entry_grace=1, dwell_threshold=15.0)
    m.update({1: INSIDE_PT}, 0, 0.0, ZONE)  # entry at t=0
    for t in (5.0, 10.0, 16.0, 20.0, 25.0):
        m.update({1: INSIDE_PT}, int(t * 30), t, ZONE)

    dwell_events = [e for e in m.events if e.type == "LONG_DWELL"]
    assert len(dwell_events) == 1  # not one per frame past threshold
    assert dwell_events[0].data["duration_sec"] >= 15.0


def test_dwell_event_deduplicated_even_with_many_more_frames():
    m = make_monitor(entry_grace=1, dwell_threshold=1.0)
    m.update({1: INSIDE_PT}, 0, 0.0, ZONE)
    for i in range(1, 100):
        m.update({1: INSIDE_PT}, i, i * 0.05, ZONE)  # runs well past the 1s threshold repeatedly
    dwell_events = [e for e in m.events if e.type == "LONG_DWELL"]
    assert len(dwell_events) == 1


def test_new_dwell_can_fire_after_a_fresh_entry():
    m = make_monitor(entry_grace=1, exit_grace=1, dwell_threshold=1.0)
    m.update({1: INSIDE_PT}, 0, 0.0, ZONE)
    m.update({1: INSIDE_PT}, 1, 2.0, ZONE)  # dwell 1 fires
    m.update({1: OUTSIDE_PT}, 2, 2.1, ZONE)  # exit
    m.update({1: INSIDE_PT}, 3, 2.2, ZONE)  # re-entry
    m.update({1: INSIDE_PT}, 4, 4.0, ZONE)  # dwell 2 fires (>1s since re-entry)

    dwell_events = [e for e in m.events if e.type == "LONG_DWELL"]
    assert len(dwell_events) == 2


def test_multiple_simultaneous_tracks_have_independent_state():
    m = make_monitor(entry_grace=1, exit_grace=1)
    m.update({12: INSIDE_PT, 17: OUTSIDE_PT}, 0, 0.0, ZONE)
    assert m.state_of(12) == INSIDE
    assert m.state_of(17) == OUTSIDE

    m.update({12: OUTSIDE_PT, 17: INSIDE_PT}, 1, 0.1, ZONE)
    assert m.state_of(12) == OUTSIDE
    assert m.state_of(17) == INSIDE

    types_by_track = {(e.track_id, e.type) for e in m.events}
    assert (12, "ZONE_ENTRY") in types_by_track
    assert (12, "ZONE_EXIT") in types_by_track
    assert (17, "ZONE_ENTRY") in types_by_track
    assert (17, "ZONE_EXIT") not in types_by_track


def test_multiple_zone_ids_are_fully_independent():
    zone_a = ZoneMonitor("zone-A", entry_grace_frames=1, exit_grace_frames=1)
    zone_b = ZoneMonitor("zone-B", entry_grace_frames=1, exit_grace_frames=1)

    # track 1 is inside zone A's polygon but outside zone B's polygon
    other_polygon = [(100, 100), (110, 100), (110, 110), (100, 110)]
    zone_a.update({1: INSIDE_PT}, 0, 0.0, ZONE)
    zone_b.update({1: INSIDE_PT}, 0, 0.0, other_polygon)

    assert zone_a.state_of(1) == INSIDE
    assert zone_b.state_of(1) == OUTSIDE
    assert all(e.zone_id == "zone-A" for e in zone_a.events)
    assert zone_b.events == []
