"""BorderWatch API - thin HTTP layer over the module pipelines.

Two job creation paths:
  - POST /api/zone-jobs: the original Phase 3 zone-only job (kept exactly
    as-is for backward compatibility - existing callers/tests are unaffected).
  - POST /api/jobs: the unified Phase 6 path - enable any subset of
    {person_id, anpr, zone(s), behavior, lowlight} and get ONE job that runs
    them all through backend.orchestrator.CombinedPipeline (one video decode,
    one tracker pass, one output video, one event stream), rather than
    requiring N separate jobs/pipeline runs for N modules.

Errors are translated to clean HTTP responses (404/400/409) with a short
message - never a raw Python traceback. Full tracebacks go to the server
log via `logger.exception` in the unhandled-exception handler.
"""
from __future__ import annotations

import dataclasses
import logging
from pathlib import Path

import cv2
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from backend.api.jobs import job_manager
from backend.api.schemas import (
    AnprModuleRequest, BehaviorModuleRequest, CombinedJobRequest, EvidenceItemOut,
    JobStatusOut, LowlightModuleRequest, PersonIdModuleRequest, PlateSearchRequest,
    ReferenceUploadOut, SystemStatusOut, VideoInfoOut, VideoUploadOut, ZoneCreateRequest,
    ZoneJobRequest, ZoneOut, ZoneUpdateRequest,
)
from backend.api.storage import (
    NotFoundError, find_reference_photos, find_video_path, load_zone, new_id,
    save_reference_photos, save_uploaded_video, save_zone,
)
from backend.config import (
    AnprConfig, BehaviorConfig, EVIDENCE_DIR, LowLightConfig, OUTPUTS_DIR, PersonIDConfig,
    SFACE_MODEL_PATH, YUNET_MODEL_PATH, YOLO_MODEL_PATH, ZoneConfig, detect_device,
)
from backend.core.video import VideoReader, extract_frame
from backend.modules.anpr.ocr import PlateOcr
from backend.modules.zone.geometry import Zone
from backend.modules.zone.pipeline import ZonePipeline
from backend.orchestrator import CombinedPipeline, OrchestratorError, OrchestratorRequest

logger = logging.getLogger("backend.app")
app = FastAPI(title="BorderWatch API")


@app.exception_handler(NotFoundError)
def _not_found_handler(request: Request, exc: NotFoundError):
    return Response(content=str(exc), status_code=404)


@app.exception_handler(OrchestratorError)
def _orchestrator_error_handler(request: Request, exc: OrchestratorError):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.exception_handler(Exception)
def _unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "internal server error"}, status_code=500)


def _job_status_out(job) -> JobStatusOut:
    return JobStatusOut(**job.progress_info())


# --- videos -----------------------------------------------------------------

@app.post("/api/videos", response_model=VideoUploadOut)
async def upload_video(file: UploadFile):
    data = await file.read()
    if not data:
        raise HTTPException(400, "uploaded file is empty")
    video_id, path = save_uploaded_video(file.filename or "upload.mp4", data)
    try:
        with VideoReader(path) as reader:
            info = reader.info
    except Exception:
        path.unlink(missing_ok=True)
        raise HTTPException(400, "could not be read as a video - unsupported or corrupted file")
    if info.frame_count <= 0:
        path.unlink(missing_ok=True)
        raise HTTPException(400, "video has no readable frames")
    return VideoUploadOut(
        video_id=video_id, filename=file.filename or path.name,
        video_info=VideoInfoOut(fps=info.fps, width=info.width, height=info.height, frame_count=info.frame_count, duration_sec=info.duration_sec),
    )


@app.get("/api/videos/{video_id}/frame")
def get_representative_frame(video_id: str, at: float = 0.5):
    path = find_video_path(video_id)
    image, _info = extract_frame(path, fraction=at)
    ok, buf = cv2.imencode(".jpg", image)
    if not ok:
        raise HTTPException(500, "failed to encode representative frame")
    return Response(content=buf.tobytes(), media_type="image/jpeg")


# --- reference photos (Target Person ID) -------------------------------------

@app.post("/api/references", response_model=ReferenceUploadOut)
async def upload_references(files: list[UploadFile]):
    if not files:
        raise HTTPException(400, "at least one reference photo is required")
    if len(files) > 6:
        raise HTTPException(400, "at most 6 reference photos are supported")
    payload = [(f.filename or "ref.jpg", await f.read()) for f in files]
    if any(not data for _, data in payload):
        raise HTTPException(400, "one or more uploaded reference photos were empty")
    ref_id, paths = save_reference_photos(payload)
    return ReferenceUploadOut(reference_set_id=ref_id, photo_count=len(paths))


# --- zones --------------------------------------------------------------------

@app.post("/api/zones", response_model=ZoneOut)
def create_zone(req: ZoneCreateRequest):
    find_video_path(req.video_id)  # 404s if the video doesn't exist
    zone = Zone(zone_id=new_id(), video_id=req.video_id, label=req.label, shape=req.shape, points=req.points)
    save_zone(zone)
    return ZoneOut(**zone.to_dict())


@app.get("/api/zones/{zone_id}", response_model=ZoneOut)
def get_zone(zone_id: str):
    zone = load_zone(zone_id)
    return ZoneOut(**zone.to_dict())


@app.put("/api/zones/{zone_id}", response_model=ZoneOut)
def update_zone(zone_id: str, req: ZoneUpdateRequest):
    existing = load_zone(zone_id)
    zone = Zone(
        zone_id=zone_id, video_id=existing.video_id,
        label=req.label if req.label is not None else existing.label,
        shape=req.shape if req.shape is not None else existing.shape,
        points=req.points if req.points is not None else existing.points,
    )
    save_zone(zone)
    return ZoneOut(**zone.to_dict())


# --- zone-only jobs (kept for backward compatibility) ------------------------

@app.post("/api/zone-jobs", response_model=JobStatusOut)
def start_zone_job(req: ZoneJobRequest):
    video_path = find_video_path(req.video_id)
    zone = load_zone(req.zone_id)

    zone_config = ZoneConfig()
    if req.config is not None:
        overrides = {k: v for k, v in req.config.model_dump().items() if v is not None}
        zone_config = dataclasses.replace(zone_config, **overrides)

    with VideoReader(video_path) as reader:
        total_frames = reader.info.frame_count
    job = job_manager.create(kind="zone", total_frames=total_frames)
    output_path = OUTPUTS_DIR / f"zone_{job.job_id}.mp4"
    job.output_path = str(output_path)

    def _run(progress_cb):
        result = ZonePipeline(config=zone_config).run(video_path, zone, output_path, progress_cb=progress_cb)
        job.events = result.events
        return {
            "zone_id": result.zone_id, "tracks_observed": result.tracks_observed,
            "entries": result.entries, "exits": result.exits, "dwell_events": result.dwell_events,
            "codec_used": result.codec_used, "browser_playable": result.browser_playable,
        }

    job_manager.start(job, _run)
    return _job_status_out(job)


# --- unified combined jobs (Phase 6) ------------------------------------------

@app.post("/api/jobs", response_model=JobStatusOut)
def start_combined_job(req: CombinedJobRequest):
    video_path = find_video_path(req.video_id)
    if not (req.person_id or req.anpr or req.zone_ids or req.behavior or req.lowlight):
        raise HTTPException(400, "at least one module must be enabled")

    orch_req = OrchestratorRequest()

    if req.person_id is not None:
        orch_req.enable_person_id = True
        orch_req.reference_photo_paths = find_reference_photos(req.person_id.reference_set_id)
        if req.person_id.config:
            orch_req.person_id_config = dataclasses.replace(PersonIDConfig(), **req.person_id.config)

    if req.anpr is not None:
        orch_req.enable_anpr = True
        orch_req.target_plate = req.anpr.target_plate
        if req.anpr.config:
            orch_req.anpr_config = dataclasses.replace(AnprConfig(), **req.anpr.config)

    if req.zone_ids:
        orch_req.zones = [load_zone(zid) for zid in req.zone_ids]

    if req.behavior is not None:
        orch_req.enable_behavior = True
        if req.behavior.config:
            orch_req.behavior_config = dataclasses.replace(BehaviorConfig(), **req.behavior.config)

    if req.lowlight is not None:
        orch_req.enable_lowlight = True
        if req.lowlight.config:
            orch_req.lowlight_config = dataclasses.replace(LowLightConfig(), **req.lowlight.config)

    with VideoReader(video_path) as reader:
        total_frames = reader.info.frame_count
    job = job_manager.create(kind="combined", total_frames=total_frames)
    output_path = OUTPUTS_DIR / f"job_{job.job_id}.mp4"
    evidence_dir = EVIDENCE_DIR / job.job_id
    orch_req.evidence_dir = evidence_dir
    job.output_path = str(output_path)
    job.evidence_dir = str(evidence_dir)

    def _run(progress_cb):
        result = CombinedPipeline(orch_req).run(video_path, output_path, progress_cb=progress_cb)
        job.events = result.events
        return {
            "modules_run": result.modules_run, "codec_used": result.codec_used,
            "browser_playable": result.browser_playable,
            "video_info": {
                "fps": result.video_info.fps, "width": result.video_info.width,
                "height": result.video_info.height, "frame_count": result.video_info.frame_count,
                "duration_sec": result.video_info.duration_sec,
            },
            "person_id": result.person_id, "anpr": result.anpr, "zones": result.zones,
            "behavior": result.behavior, "lowlight": result.lowlight,
        }

    job_manager.start(job, _run)
    return _job_status_out(job)


@app.post("/api/anpr/search", response_model=JobStatusOut)
def start_plate_search(req: PlateSearchRequest):
    """Convenience wrapper: 'is this plate present in the video?' - equivalent
    to POST /api/jobs with only anpr enabled and target_plate set."""
    video_path = find_video_path(req.video_id)
    anpr_module = AnprModuleRequest(target_plate=req.plate, config=req.config)
    return start_combined_job(CombinedJobRequest(video_id=req.video_id, anpr=anpr_module))


# --- jobs (shared by both job kinds) ------------------------------------------

@app.get("/api/jobs", response_model=list[JobStatusOut])
def list_jobs():
    jobs = sorted(job_manager.list(), key=lambda j: j.created_at, reverse=True)
    return [_job_status_out(j) for j in jobs]


@app.get("/api/jobs/{job_id}", response_model=JobStatusOut)
def get_job(job_id: str):
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(404, f"job not found: {job_id}")
    return _job_status_out(job)


@app.post("/api/jobs/{job_id}/cancel", response_model=JobStatusOut)
def cancel_job(job_id: str):
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(404, f"job not found: {job_id}")
    ok = job_manager.cancel(job)
    if not ok:
        raise HTTPException(409, f"job cannot be cancelled (status={job.status})")
    return _job_status_out(job)


@app.get("/api/jobs/{job_id}/events")
def get_job_events(job_id: str):
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(404, f"job not found: {job_id}")
    if job.status != "done":
        raise HTTPException(409, f"job is not finished (status={job.status})")
    return job.events


@app.get("/api/jobs/{job_id}/output")
def get_job_output(job_id: str):
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(404, f"job not found: {job_id}")
    if job.status != "done":
        raise HTTPException(409, f"job is not finished (status={job.status})")
    if job.output_path is None or not Path(job.output_path).is_file():
        raise HTTPException(404, "output video not found")
    return FileResponse(job.output_path, media_type="video/mp4")


@app.get("/api/jobs/{job_id}/evidence", response_model=list[EvidenceItemOut])
def list_job_evidence(job_id: str):
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(404, f"job not found: {job_id}")
    if not job.evidence_dir or not Path(job.evidence_dir).is_dir():
        return []
    items = []
    for path in sorted(Path(job.evidence_dir).glob("*.jpg")):
        parts = path.stem.split("_")
        track_id = int(parts[0]) if parts and parts[0].isdigit() else None
        frame_index = int(parts[-1]) if parts and parts[-1].isdigit() else None
        event_type = "_".join(parts[1:-1]) if len(parts) > 2 else None
        items.append(EvidenceItemOut(filename=path.name, track_id=track_id, event_type=event_type, frame_index=frame_index))
    return items


@app.get("/api/jobs/{job_id}/evidence/{filename}")
def get_job_evidence_file(job_id: str, filename: str):
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(404, f"job not found: {job_id}")
    if not job.evidence_dir:
        raise HTTPException(404, "no evidence for this job")
    path = Path(job.evidence_dir) / Path(filename).name  # basename only - no path traversal
    if not path.is_file():
        raise HTTPException(404, "evidence file not found")
    return FileResponse(path, media_type="image/jpeg")


# --- system status -------------------------------------------------------

@app.get("/api/system/status", response_model=SystemStatusOut)
def system_status():
    ocr = PlateOcr()
    jobs = job_manager.list()
    return SystemStatusOut(
        device=detect_device(),
        ocr_available=ocr.available, ocr_status=ocr.status.to_dict(),
        models_present={
            "yunet": YUNET_MODEL_PATH.is_file(), "sface": SFACE_MODEL_PATH.is_file(), "yolo": YOLO_MODEL_PATH.is_file(),
        },
        active_jobs=sum(1 for j in jobs if j.status in ("pending", "running")),
        total_jobs=len(jobs),
    )
