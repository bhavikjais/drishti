from unittest.mock import patch

import httpx

from backend.config import AlertConfig
from backend.core.alerts import DEFAULT_ALERT_EVENT_TYPES, dispatch_alert


def make_event(event_type="TARGET_CONFIRMED", **overrides) -> dict:
    event = {
        "event_id": "evt_1", "type": event_type, "track_id": 5,
        "frame_index": 100, "timestamp_sec": 4.0, "zone": None, "data": {"votes": 2},
    }
    event.update(overrides)
    return event


def test_disabled_config_does_not_dispatch():
    cfg = AlertConfig(enabled=False, webhook_url="https://example.com/hook")
    with patch("backend.core.alerts.httpx.post") as mock_post:
        future = dispatch_alert(cfg, "job1", make_event())
    assert future is None
    mock_post.assert_not_called()


def test_missing_webhook_url_does_not_dispatch():
    cfg = AlertConfig(enabled=True, webhook_url=None)
    with patch("backend.core.alerts.httpx.post") as mock_post:
        future = dispatch_alert(cfg, "job1", make_event())
    assert future is None
    mock_post.assert_not_called()


def test_non_qualifying_event_type_does_not_dispatch():
    cfg = AlertConfig(enabled=True, webhook_url="https://example.com/hook")
    with patch("backend.core.alerts.httpx.post") as mock_post:
        future = dispatch_alert(cfg, "job1", make_event(event_type="ZONE_ENTRY"))
        assert future is None
    mock_post.assert_not_called()


def test_qualifying_event_posts_expected_payload():
    cfg = AlertConfig(enabled=True, webhook_url="https://example.com/hook")
    with patch("backend.core.alerts.httpx.post") as mock_post:
        mock_post.return_value.status_code = 200
        future = dispatch_alert(cfg, "job1", make_event())
        assert future is not None
        future.result(timeout=5)  # wait for the background thread to finish

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://example.com/hook"
    payload = kwargs["json"]
    assert payload["job_id"] == "job1"
    assert payload["type"] == "TARGET_CONFIRMED"
    assert payload["track_id"] == 5
    assert payload["data"] == {"votes": 2}


def test_custom_event_types_override_default():
    cfg = AlertConfig(enabled=True, webhook_url="https://example.com/hook", event_types=frozenset({"ZONE_ENTRY"}))
    with patch("backend.core.alerts.httpx.post") as mock_post:
        mock_post.return_value.status_code = 200
        future_zone = dispatch_alert(cfg, "job1", make_event(event_type="ZONE_ENTRY"))
        future_target = dispatch_alert(cfg, "job1", make_event(event_type="TARGET_CONFIRMED"))
        assert future_zone is not None
        future_zone.result(timeout=5)
        assert future_target is None
    mock_post.assert_called_once()


def test_network_failure_is_swallowed_not_raised():
    cfg = AlertConfig(enabled=True, webhook_url="https://example.com/hook")
    with patch("backend.core.alerts.httpx.post", side_effect=httpx.ConnectError("refused")):
        future = dispatch_alert(cfg, "job1", make_event())
        future.result(timeout=5)  # must not raise despite the underlying failure


def test_http_error_status_is_logged_not_raised():
    cfg = AlertConfig(enabled=True, webhook_url="https://example.com/hook")
    with patch("backend.core.alerts.httpx.post") as mock_post:
        mock_post.return_value.status_code = 500
        future = dispatch_alert(cfg, "job1", make_event())
        future.result(timeout=5)  # must not raise despite the 500


def test_default_alert_event_types_cover_target_events_only():
    assert "TARGET_CONFIRMED" in DEFAULT_ALERT_EVENT_TYPES
    assert "TARGET_ZONE_INTRUSION_PREDICTED" in DEFAULT_ALERT_EVENT_TYPES
    assert "ZONE_ENTRY" not in DEFAULT_ALERT_EVENT_TYPES
    assert "PLATE_DETECTED" not in DEFAULT_ALERT_EVENT_TYPES
