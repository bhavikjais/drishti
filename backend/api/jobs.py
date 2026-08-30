"""In-process background job runner.

Video processing is synchronous CPU-bound work, so jobs run on a plain
Python thread (not FastAPI's async loop) with progress reported back through
a callback the pipeline already calls periodically. This is intentionally
simple - a single-process, single-machine job runner; a real multi-worker
deployment would need a real task queue (Celery/RQ) instead, noted as a
known limitation, not built here.

Job state is in-memory (self._jobs) for live polling, but every status
transition is also written to disk under a manifest directory - so
uploaded videos/output videos/evidence (already files on disk) stay linked
to their job's metadata (status, events, summary) across an API restart,
without standing up a real database for this prototype. A job caught
"running" in a manifest from a previous process (the thread that was
running it is gone) is reinterpreted as failed/interrupted on load, rather
than lying that it's still in progress forever.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from backend.config import JOBS_DIR


class JobCancelled(Exception):
    pass


@dataclass
class Job:
    job_id: str
    kind: str
    status: str = "pending"  # pending | running | done | failed | cancelled
    progress: float = 0.0
    total_frames: int | None = None
    error: str | None = None
    result: dict | None = None
    events: list[dict] = field(default_factory=list)
    output_path: str | None = None
    evidence_dir: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False, compare=False)

    def progress_info(self) -> dict:
        now = time.time()
        elapsed = (self.finished_at or now) - self.started_at if self.started_at else 0.0
        eta_sec = None
        if self.status == "running" and self.progress > 0.01:
            eta_sec = max(0.0, elapsed / self.progress - elapsed)
        frames_processed = int(round(self.progress * self.total_frames)) if self.total_frames else None
        processing_fps = round(frames_processed / elapsed, 2) if frames_processed and elapsed > 0 else None
        return {
            "job_id": self.job_id, "kind": self.kind, "status": self.status,
            "progress": round(self.progress, 4), "frames_processed": frames_processed,
            "total_frames": self.total_frames, "processing_fps": processing_fps,
            "elapsed_sec": round(elapsed, 2), "eta_sec": round(eta_sec, 2) if eta_sec is not None else None,
            "error": self.error, "summary": self.result,
        }

    def to_manifest(self) -> dict:
        # Built manually (not dataclasses.asdict()) - asdict() deep-copies
        # every field before returning, and threading.Event contains a lock
        # that can't be deep-copied/pickled, which crashed this on every
        # persist call once a job actually had a cancel_event.
        return {
            "job_id": self.job_id, "kind": self.kind, "status": self.status,
            "progress": self.progress, "total_frames": self.total_frames,
            "error": self.error, "result": self.result, "events": self.events,
            "output_path": self.output_path, "evidence_dir": self.evidence_dir,
            "created_at": self.created_at, "started_at": self.started_at, "finished_at": self.finished_at,
        }


class JobManager:
    def __init__(self, persist_dir: Path | None = None):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self.persist_dir = persist_dir
        if self.persist_dir is not None:
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            self._load_persisted()

    def _load_persisted(self) -> None:
        for path in sorted(self.persist_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text())
            except Exception:
                continue
            data.pop("cancel_event", None)
            job = Job(**{k: v for k, v in data.items() if k in Job.__dataclass_fields__})
            if job.status in ("pending", "running"):
                job.status = "failed"
                job.error = "interrupted by server restart"
                job.finished_at = job.finished_at or time.time()
            self._jobs[job.job_id] = job

    def _persist(self, job: Job) -> None:
        if self.persist_dir is None:
            return
        path = self.persist_dir / f"{job.job_id}.json"
        path.write_text(json.dumps(job.to_manifest(), default=str, indent=2))

    def create(self, kind: str, total_frames: int | None = None) -> Job:
        job = Job(job_id=uuid.uuid4().hex, kind=kind, total_frames=total_frames)
        with self._lock:
            self._jobs[job.job_id] = job
        self._persist(job)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    def start(self, job: Job, target: Callable[[Callable[[float], None]], dict]) -> None:
        """Runs `target(progress_cb)` on a background thread. `target` must
        return a dict result on success, or raise on failure. progress_cb
        also checks job.cancel_event and raises JobCancelled if it was set -
        cancellation is cooperative, checked wherever the pipeline already
        reports progress (bounded latency, no busy-polling)."""
        def progress_cb(p: float) -> None:
            if job.cancel_event.is_set():
                raise JobCancelled("cancelled by user")
            job.progress = p

        def _worker():
            job.status = "running"
            job.started_at = time.time()
            self._persist(job)
            try:
                result = target(progress_cb)
                job.result = result
                job.progress = 1.0
                job.status = "done"
            except JobCancelled:
                job.status = "cancelled"
                job.error = "cancelled by user"
            except Exception as exc:
                job.status = "failed"
                job.error = str(exc)
            finally:
                job.finished_at = time.time()
                self._persist(job)

        threading.Thread(target=_worker, daemon=True).start()

    def cancel(self, job: Job) -> bool:
        if job.status not in ("pending", "running"):
            return False
        job.cancel_event.set()
        return True


job_manager = JobManager(persist_dir=JOBS_DIR)
