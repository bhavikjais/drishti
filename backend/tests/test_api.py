"""End-to-end API test: upload -> representative frame -> create/update zone
-> start a zone job -> poll to completion -> fetch events -> fetch output
video, all through the real FastAPI app (in-process TestClient, no network).
Reuses the Phase 1 person-ID smoke fixture (real 3s pedestrian clip) so this
also doubles as a real (if small) end-to-end video-analysis run through the
HTTP layer, not just mocked plumbing.
"""
import time

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.config import REPO_ROOT

client = TestClient(app)
VIDEO_PATH = REPO_ROOT / "uploads" / "smoke_person_id.mp4"

pytestmark = pytest.mark.skipif(not VIDEO_PATH.exists(), reason="phase-1 smoke fixture not present")


def _poll_job(job_id, timeout_sec=180):
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        resp = client.get(f"/api/jobs/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(1.0)
    raise TimeoutError(f"job {job_id} did not finish within {timeout_sec}s")


def test_full_zone_workflow_through_the_api():
    # 1) upload
    with open(VIDEO_PATH, "rb") as f:
        resp = client.post("/api/videos", files={"file": ("smoke.mp4", f, "video/mp4")})
    assert resp.status_code == 200, resp.text
    video = resp.json()
    video_id = video["video_id"]
    assert video["video_info"]["frame_count"] == 180
    assert video["video_info"]["width"] == 960
    assert video["video_info"]["height"] == 540

    # 2) representative frame
    resp = client.get(f"/api/videos/{video_id}/frame", params={"at": 0.5})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    arr = np.frombuffer(resp.content, dtype=np.uint8)
    decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    assert decoded.shape[1] == 960 and decoded.shape[0] == 540

    # 3) create a zone covering the right half of the frame (rectangle)
    resp = client.post("/api/zones", json={
        "video_id": video_id, "shape": "rectangle",
        "points": [[0.5, 0.0], [1.0, 1.0]], "label": "Right Half",
    })
    assert resp.status_code == 200, resp.text
    zone = resp.json()
    zone_id = zone["zone_id"]
    assert zone["shape"] == "rectangle"

    # 3b) update it
    resp = client.put(f"/api/zones/{zone_id}", json={"label": "Updated Label"})
    assert resp.status_code == 200
    assert resp.json()["label"] == "Updated Label"
    assert resp.json()["points"] == [[0.5, 0.0], [1.0, 1.0]]  # unspecified fields unchanged

    # 4) start a zone analysis job with a short dwell threshold so it's
    # exercisable within this short clip
    resp = client.post("/api/zone-jobs", json={
        "video_id": video_id, "zone_id": zone_id,
        "config": {"entry_grace_frames": 2, "exit_grace_frames": 5, "dwell_threshold_sec": 0.5},
    })
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]
    assert resp.json()["status"] in ("pending", "running")

    # 5) poll to completion
    job = _poll_job(job_id)
    assert job["status"] == "done", job.get("error")
    assert job["progress"] == 1.0
    assert job["summary"]["zone_id"] == zone_id
    assert job["summary"]["browser_playable"] is True

    # 6) events
    resp = client.get(f"/api/jobs/{job_id}/events")
    assert resp.status_code == 200
    events = resp.json()
    assert isinstance(events, list)
    for e in events:
        assert e["type"] in ("ZONE_ENTRY", "ZONE_EXIT", "LONG_DWELL")
        assert e["zone_id"] == zone_id

    # 7) output video - fetch and verify it's a real, complete, playable file
    resp = client.get(f"/api/jobs/{job_id}/output")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "video/mp4"
    out_path = REPO_ROOT / "outputs" / f"_api_test_output_{job_id}.mp4"
    out_path.write_bytes(resp.content)
    cap = cv2.VideoCapture(str(out_path))
    assert cap.isOpened()
    assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 180
    assert abs(cap.get(cv2.CAP_PROP_FPS) - 60.0) < 1.0
    cap.release()
    out_path.unlink()


def test_missing_video_returns_404():
    resp = client.get("/api/videos/does-not-exist/frame")
    assert resp.status_code == 404


def test_missing_zone_returns_404():
    resp = client.get("/api/zones/does-not-exist")
    assert resp.status_code == 404


def test_missing_job_returns_404():
    resp = client.get("/api/jobs/does-not-exist")
    assert resp.status_code == 404
