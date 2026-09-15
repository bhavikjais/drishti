"""Webhook alert dispatch: fires a JSON POST to a user-configured URL for
qualifying events (target confirmed, predicted zone intrusion, etc.), so an
operator watching Slack/Discord/Teams (or their own endpoint) gets notified
without staring at the Drishti tab.

Dispatched from a small background thread pool - never inline in the video
processing loop. A slow or unreachable webhook endpoint must never stall
frame processing; the orchestrator calls dispatch_alert() once per
qualifying event AFTER a job's full event list is known (see
orchestrator.py), matching this project's honest "no partial/incremental
event feed" architecture (see pages/Processing.tsx's docstring on the
frontend) - a batch job gets a batch of notifications when it finishes, not
a fake live stream mid-run.

Failures (network error, non-2xx response, bad URL) are logged and
swallowed, never raised: alerting is a best-effort side channel, not a
correctness-critical part of the job.
"""
from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor

import httpx

from backend.config import AlertConfig

logger = logging.getLogger("backend.core.alerts")

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="alert-webhook")

# Target-related events only - not routine ZONE_ENTRY/PLATE_DETECTED noise
# that would flood a Slack channel on every ordinary detection.
DEFAULT_ALERT_EVENT_TYPES: frozenset[str] = frozenset({
    "TARGET_CONFIRMED", "TARGET_REACQUIRED", "TARGET_LOST",
    "TARGET_VEHICLE_FOUND", "TARGET_VEHICLE_REACQUIRED", "TARGET_VEHICLE_LOST",
    "TARGET_ZONE_INTRUSION", "TARGET_ZONE_INTRUSION_PREDICTED",
    "TARGET_BEHAVIOR_ALERT",
})


def _post(url: str, payload: dict, timeout: float) -> None:
    try:
        response = httpx.post(url, json=payload, timeout=timeout)
        if response.status_code >= 400:
            logger.warning("Alert webhook %s returned HTTP %s", url, response.status_code)
    except Exception as exc:
        logger.warning("Alert webhook %s failed: %s", url, exc)


def dispatch_alert(config: AlertConfig, job_id: str, event: dict) -> Future | None:
    """Fire-and-forget: submits the webhook POST to a background thread and
    returns immediately. Returns the submitted Future (tests can wait on it
    with .result()); returns None if nothing was dispatched (disabled, no
    URL configured, or this event type isn't one that should alert)."""
    if not config.enabled or not config.webhook_url:
        return None
    event_types = config.event_types if config.event_types is not None else DEFAULT_ALERT_EVENT_TYPES
    if event.get("type") not in event_types:
        return None

    payload = {
        "job_id": job_id, "event_id": event.get("event_id"), "type": event["type"],
        "track_id": event.get("track_id"), "frame_index": event.get("frame_index"),
        "timestamp_sec": event.get("timestamp_sec"), "zone": event.get("zone"),
        "data": event.get("data", {}),
    }
    return _executor.submit(_post, config.webhook_url, payload, config.timeout_sec)
