import threading
import time

from backend.api.jobs import JobManager


def test_job_lifecycle_completes_successfully(tmp_path):
    jm = JobManager(persist_dir=tmp_path)
    job = jm.create("test", total_frames=100)
    assert job.status == "pending"

    def target(progress_cb):
        progress_cb(0.5)
        progress_cb(1.0)
        return {"ok": True}

    jm.start(job, target)
    for _ in range(50):
        if job.status in ("done", "failed", "cancelled"):
            break
        time.sleep(0.05)
    assert job.status == "done"
    assert job.result == {"ok": True}
    assert job.progress == 1.0


def test_job_failure_is_captured_not_raised(tmp_path):
    jm = JobManager(persist_dir=tmp_path)
    job = jm.create("test")

    def target(progress_cb):
        raise ValueError("boom")

    jm.start(job, target)
    for _ in range(50):
        if job.status in ("done", "failed", "cancelled"):
            break
        time.sleep(0.05)
    assert job.status == "failed"
    assert "boom" in job.error


def test_job_cancellation_stops_processing(tmp_path):
    jm = JobManager(persist_dir=tmp_path)
    job = jm.create("test", total_frames=1000)
    started = threading.Event()
    stopped_early = threading.Event()

    def target(progress_cb):
        started.set()
        for i in range(1000):
            progress_cb(i / 1000)  # will raise JobCancelled once cancel_event is set
            time.sleep(0.001)
        stopped_early.set()  # should never reach here
        return {"frames": 1000}

    jm.start(job, target)
    started.wait(timeout=2.0)
    time.sleep(0.02)
    ok = jm.cancel(job)
    assert ok is True

    for _ in range(100):
        if job.status in ("done", "failed", "cancelled"):
            break
        time.sleep(0.05)
    assert job.status == "cancelled"
    assert not stopped_early.is_set()  # actually stopped, didn't run to completion


def test_cancelling_a_finished_job_returns_false(tmp_path):
    jm = JobManager(persist_dir=tmp_path)
    job = jm.create("test")
    jm.start(job, lambda progress_cb: {"ok": True})
    for _ in range(50):
        if job.status == "done":
            break
        time.sleep(0.05)
    assert jm.cancel(job) is False


def test_progress_info_reports_frames_and_fps(tmp_path):
    jm = JobManager(persist_dir=tmp_path)
    job = jm.create("test", total_frames=200)
    job.status = "running"
    job.started_at = time.time() - 2.0  # pretend 2s have elapsed
    job.progress = 0.5
    info = job.progress_info()
    assert info["total_frames"] == 200
    assert info["frames_processed"] == 100
    assert info["processing_fps"] is not None
    assert info["eta_sec"] is not None


def test_job_manifest_persists_across_manager_restart(tmp_path):
    jm1 = JobManager(persist_dir=tmp_path)
    job = jm1.create("test", total_frames=10)

    def target(progress_cb):
        progress_cb(1.0)
        return {"done_marker": True}

    jm1.start(job, target)
    for _ in range(50):
        if job.status == "done":
            break
        time.sleep(0.05)
    assert job.status == "done"

    # simulate an API restart: fresh JobManager reading the same persist_dir
    jm2 = JobManager(persist_dir=tmp_path)
    reloaded = jm2.get(job.job_id)
    assert reloaded is not None
    assert reloaded.status == "done"
    assert reloaded.result == {"done_marker": True}


def test_interrupted_running_job_is_reinterpreted_as_failed_on_restart(tmp_path):
    jm1 = JobManager(persist_dir=tmp_path)
    job = jm1.create("test")
    job.status = "running"
    job.started_at = time.time()
    jm1._persist(job)  # simulate the process dying mid-run, no terminal state ever written

    jm2 = JobManager(persist_dir=tmp_path)
    reloaded = jm2.get(job.job_id)
    assert reloaded.status == "failed"
    assert "interrupted" in reloaded.error
