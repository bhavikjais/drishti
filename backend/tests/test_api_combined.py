"""Tests for the Phase 6 unified API surface: reference upload, the
combined multi-module job endpoint, cancellation, evidence, plate search,
system status, and error handling - all through the real FastAPI app via
TestClient (no internal pipeline scripts), matching the task's "must work
without manually running internal Python scripts" requirement.
"""
import time

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.config import REPO_ROOT

client = TestClient(app)
PERSON_VIDEO = REPO_ROOT / "uploads" / "smoke_person_id.mp4"
ANPR_VIDEO = REPO_ROOT / "uploads" / "smoke_anpr_test123.mp4"
REF1 = REPO_ROOT / "references" / "smoke_target" / "ref1.jpg"
REF2 = REPO_ROOT / "references" / "smoke_target" / "ref2.jpg"

pytestmark = pytest.mark.skipif(not PERSON_VIDEO.exists(), reason="phase fixtures not present")


def _poll_job(job_id, timeout_sec=180):
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        resp = client.get(f"/api/jobs/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        if body["status"] in ("done", "failed", "cancelled"):
            return body
        time.sleep(1.0)
    raise TimeoutError(f"job {job_id} did not finish within {timeout_sec}s")


def _upload_video(path) -> str:
    with open(path, "rb") as f:
        resp = client.post("/api/videos", files={"file": (path.name, f, "video/mp4")})
    assert resp.status_code == 200, resp.text
    return resp.json()["video_id"]


def _upload_references(paths) -> str:
    files = [("files", (p.name, open(p, "rb"), "image/jpeg")) for p in paths]
    resp = client.post("/api/references", files=files)
    for _, (_, fh, _) in files:
        fh.close()
    assert resp.status_code == 200, resp.text
    return resp.json()["reference_set_id"]


def test_list_jobs_endpoint_returns_created_job_and_is_newest_first():
    video_id = _upload_video(PERSON_VIDEO)
    resp = client.post("/api/jobs", json={"video_id": video_id, "behavior": {}})
    job_id = resp.json()["job_id"]

    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    jobs = resp.json()
    assert any(j["job_id"] == job_id for j in jobs)
    ids = [j["job_id"] for j in jobs]
    assert ids.index(job_id) == 0  # most recently created appears first
    _poll_job(job_id)  # let the background thread finish before the test process exits


def test_system_status_endpoint():
    resp = client.get("/api/system/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["device"] in ("cpu", "cuda")
    assert body["models_present"]["yunet"] is True
    assert body["models_present"]["sface"] is True
    assert body["models_present"]["yolo"] is True
    assert isinstance(body["ocr_available"], bool)


def test_reference_upload_workflow():
    ref_id = _upload_references([REF1, REF2])
    assert ref_id

    resp = client.get(f"/api/videos/does-not-exist/frame")
    assert resp.status_code == 404  # sanity: unrelated 404 still works


def test_reference_upload_rejects_too_many_photos():
    files = [("files", (f"r{i}.jpg", open(REF1, "rb"), "image/jpeg")) for i in range(7)]
    resp = client.post("/api/references", files=files)
    for _, (_, fh, _) in files:
        fh.close()
    assert resp.status_code == 400


def test_combined_job_person_id_zone_behavior_through_api():
    video_id = _upload_video(PERSON_VIDEO)
    ref_id = _upload_references([REF1])

    resp = client.post("/api/zones", json={
        "video_id": video_id, "shape": "rectangle",
        "points": [[550 / 960, 0.0], [850 / 960, 1.0]], "label": "Restricted",
    })
    assert resp.status_code == 200
    zone_id = resp.json()["zone_id"]

    resp = client.post("/api/jobs", json={
        "video_id": video_id,
        "person_id": {"reference_set_id": ref_id},
        "zone_ids": [zone_id],
        "behavior": {"config": {"loitering_seconds": 0.5, "loitering_radius_px": 40.0, "behavior_cooldown_seconds": 1.0}},
    })
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]

    job = _poll_job(job_id)
    assert job["status"] == "done", job.get("error")
    assert job["frames_processed"] == 180
    assert job["total_frames"] == 180
    assert job["processing_fps"] is not None and job["processing_fps"] > 0
    summary = job["summary"]
    assert set(summary["modules_run"]) == {"person_id", "zone", "behavior"}
    assert summary["person_id"]["confirmed"] is True  # same fixture Phase 1 verified confirms
    assert summary["zones"][0]["zone_id"] == zone_id
    assert summary["video_info"]["frame_count"] == 180
    assert abs(summary["video_info"]["fps"] - 60.0) < 0.5

    events = client.get(f"/api/jobs/{job_id}/events").json()
    assert isinstance(events, list) and len(events) > 0
    assert all("event_id" in e for e in events)
    # person_id is confirmed (asserted above) - TARGET_CONFIRMED must actually
    # appear in the merged event stream, not just in the summary.
    assert any(e["type"] == "TARGET_CONFIRMED" for e in events)

    evidence = client.get(f"/api/jobs/{job_id}/evidence").json()
    assert isinstance(evidence, list)
    if evidence:
        fname = evidence[0]["filename"]
        file_resp = client.get(f"/api/jobs/{job_id}/evidence/{fname}")
        assert file_resp.status_code == 200
        assert file_resp.headers["content-type"] == "image/jpeg"

    out = client.get(f"/api/jobs/{job_id}/output")
    assert out.status_code == 200
    arr = np.frombuffer(out.content, dtype=np.uint8)
    tmp_path = REPO_ROOT / "outputs" / f"_test_combined_{job_id}.mp4"
    tmp_path.write_bytes(out.content)
    cap = cv2.VideoCapture(str(tmp_path))
    assert cap.isOpened()
    assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 180
    cap.release()
    tmp_path.unlink()


def test_plate_search_convenience_endpoint_found():
    video_id = _upload_video(ANPR_VIDEO)
    resp = client.post("/api/anpr/search", json={"video_id": video_id, "plate": "TEST123"})
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]
    job = _poll_job(job_id)
    assert job["status"] == "done", job.get("error")
    target = job["summary"]["anpr"]["target"]
    assert target["found"] is True
    assert target["plate_text"] == "TEST123"
    assert target["track_id"] is not None
    assert target["first_seen_sec"] is not None
    assert target["last_seen_sec"] is not None


def test_plate_search_convenience_endpoint_not_found():
    video_id = _upload_video(ANPR_VIDEO)
    resp = client.post("/api/anpr/search", json={"video_id": video_id, "plate": "ZZZ000"})
    job_id = resp.json()["job_id"]
    job = _poll_job(job_id)
    assert job["status"] == "done"
    assert job["summary"]["anpr"]["target"]["found"] is False


def test_job_cancellation_through_api():
    video_id = _upload_video(PERSON_VIDEO)
    resp = client.post("/api/jobs", json={"video_id": video_id, "behavior": {}})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    time.sleep(1.5)  # let it get partway through the 180-frame clip
    cancel_resp = client.post(f"/api/jobs/{job_id}/cancel")
    assert cancel_resp.status_code == 200

    job = _poll_job(job_id, timeout_sec=60)
    assert job["status"] == "cancelled"
    assert job["frames_processed"] is not None and job["frames_processed"] < 180


def test_cancelling_a_completed_job_returns_409():
    video_id = _upload_video(PERSON_VIDEO)
    ref_id = _upload_references([REF1])
    resp = client.post("/api/jobs", json={"video_id": video_id, "person_id": {"reference_set_id": ref_id}})
    job_id = resp.json()["job_id"]
    _poll_job(job_id)
    cancel_resp = client.post(f"/api/jobs/{job_id}/cancel")
    assert cancel_resp.status_code == 409


def test_job_with_no_modules_enabled_returns_400():
    video_id = _upload_video(PERSON_VIDEO)
    resp = client.post("/api/jobs", json={"video_id": video_id})
    assert resp.status_code == 400


def test_reference_set_not_found_returns_404():
    video_id = _upload_video(PERSON_VIDEO)
    resp = client.post("/api/jobs", json={"video_id": video_id, "person_id": {"reference_set_id": "does-not-exist"}})
    assert resp.status_code == 404


def test_missing_face_in_reference_photo_fails_job_gracefully_not_a_traceback(tmp_path):
    video_id = _upload_video(PERSON_VIDEO)
    blank_path = tmp_path / "blank.jpg"
    cv2.imwrite(str(blank_path), np.full((200, 200, 3), 128, dtype=np.uint8))
    ref_id = _upload_references([blank_path])

    resp = client.post("/api/jobs", json={"video_id": video_id, "person_id": {"reference_set_id": ref_id}})
    assert resp.status_code == 200  # job accepted; the failure surfaces async
    job_id = resp.json()["job_id"]
    job = _poll_job(job_id)
    assert job["status"] == "failed"
    assert job["error"]  # a real message
    assert "Traceback" not in job["error"]  # not a raw Python traceback


def test_invalid_video_file_is_rejected_at_upload():
    resp = client.post("/api/videos", files={"file": ("not_a_video.mp4", b"this is not a real video file", "video/mp4")})
    assert resp.status_code == 400


DARK_VIDEO = REPO_ROOT / "uploads" / "smoke_person_id_dark.mp4"


@pytest.mark.skipif(not DARK_VIDEO.exists(), reason="phase 5 dark fixture not present")
def test_final_release_gate_all_five_modules_combined_through_api():
    """The Phase 6 final release-gate test: Target Person + ANPR + Zone +
    Behavior + Low-Light, all enabled in ONE job, on a real (synthetically
    darkened, per Phase 5) video, driven entirely through the HTTP API -
    upload, configure, start, poll progress, complete, play output, read
    events, read evidence. No internal pipeline scripts involved.
    """
    video_id = _upload_video(DARK_VIDEO)
    ref_id = _upload_references([REF1])

    resp = client.post("/api/zones", json={
        "video_id": video_id, "shape": "rectangle",
        "points": [[550 / 960, 0.0], [850 / 960, 1.0]], "label": "Restricted",
    })
    zone_id = resp.json()["zone_id"]

    resp = client.post("/api/jobs", json={
        "video_id": video_id,
        "person_id": {"reference_set_id": ref_id},
        "anpr": {},
        "zone_ids": [zone_id],
        "behavior": {"config": {"loitering_seconds": 0.5, "loitering_radius_px": 40.0, "behavior_cooldown_seconds": 1.0}},
        "lowlight": {},
    })
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]

    job = _poll_job(job_id, timeout_sec=240)
    assert job["status"] == "done", job.get("error")
    assert set(job["summary"]["modules_run"]) == {"person_id", "anpr", "zone", "behavior", "lowlight"}

    # source vs output metadata must match
    assert job["total_frames"] == 180
    assert job["frames_processed"] == 180

    summary = job["summary"]
    assert summary["lowlight"]["low_light_detected"] is True
    assert summary["lowlight"]["enhancement_applied"] is True
    assert summary["person_id"] is not None
    assert summary["anpr"] is not None  # ran (0 vehicles is a legitimate real result in a pedestrian scene)
    assert summary["zones"][0]["zone_id"] == zone_id
    assert summary["behavior"]["event_counts"]

    events = client.get(f"/api/jobs/{job_id}/events").json()
    assert len(events) > 0
    event_types = {e["type"] for e in events}
    assert event_types  # non-empty, real events generated

    evidence = client.get(f"/api/jobs/{job_id}/evidence").json()
    assert isinstance(evidence, list)

    out = client.get(f"/api/jobs/{job_id}/output")
    assert out.status_code == 200
    assert out.headers["content-type"] == "video/mp4"
    tmp_path = REPO_ROOT / "outputs" / f"_test_release_gate_{job_id}.mp4"
    tmp_path.write_bytes(out.content)
    cap = cv2.VideoCapture(str(tmp_path))
    assert cap.isOpened()
    src_frames, src_fps = 180, 60.0
    out_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    out_fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    assert out_frames == src_frames
    assert abs(out_fps - src_fps) < 0.5
    tmp_path.unlink()
