from backend.core.events import EventBus


def test_duplicate_event_within_cooldown_is_dropped():
    bus = EventBus()
    e1 = bus.emit("VEHICLE_DETECTED", track_id=1, frame_index=0, timestamp_sec=0.0, cooldown_sec=5.0)
    e2 = bus.emit("VEHICLE_DETECTED", track_id=1, frame_index=10, timestamp_sec=1.0, cooldown_sec=5.0)
    assert e1 is not None
    assert e2 is None  # within cooldown window, same track+type
    assert len(bus.events) == 1


def test_event_after_cooldown_elapses_is_emitted():
    bus = EventBus()
    bus.emit("VEHICLE_DETECTED", track_id=1, frame_index=0, timestamp_sec=0.0, cooldown_sec=2.0)
    e2 = bus.emit("VEHICLE_DETECTED", track_id=1, frame_index=90, timestamp_sec=3.0, cooldown_sec=2.0)
    assert e2 is not None
    assert len(bus.events) == 2


def test_different_track_ids_are_not_deduplicated_together():
    bus = EventBus()
    bus.emit("PLATE_READ", track_id=1, frame_index=0, timestamp_sec=0.0, cooldown_sec=5.0)
    e2 = bus.emit("PLATE_READ", track_id=2, frame_index=1, timestamp_sec=0.03, cooldown_sec=5.0)
    assert e2 is not None
    assert len(bus.events) == 2


def test_state_transition_bypasses_cooldown():
    bus = EventBus()
    bus.emit("ZONE_EVENT", track_id=1, frame_index=0, timestamp_sec=0.0, cooldown_sec=10.0, state="ENTER")
    # a real state change (ENTER -> DWELL) should not be suppressed by cooldown
    e2 = bus.emit("ZONE_EVENT", track_id=1, frame_index=5, timestamp_sec=0.5, cooldown_sec=10.0, state="DWELL")
    assert e2 is not None
    assert len(bus.events) == 2
