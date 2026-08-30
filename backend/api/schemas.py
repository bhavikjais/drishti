from __future__ import annotations

from pydantic import BaseModel, Field


class VideoInfoOut(BaseModel):
    fps: float
    width: int
    height: int
    frame_count: int
    duration_sec: float


class VideoUploadOut(BaseModel):
    video_id: str
    filename: str
    video_info: VideoInfoOut


class ZoneCreateRequest(BaseModel):
    video_id: str
    shape: str = Field(pattern="^(rectangle|polygon)$")
    points: list[tuple[float, float]]
    label: str = ""


class ZoneUpdateRequest(BaseModel):
    shape: str | None = Field(default=None, pattern="^(rectangle|polygon)$")
    points: list[tuple[float, float]] | None = None
    label: str | None = None


class ZoneOut(BaseModel):
    zone_id: str
    video_id: str
    label: str
    shape: str
    points: list[tuple[float, float]]


class ZoneJobConfig(BaseModel):
    entry_grace_frames: int | None = None
    exit_grace_frames: int | None = None
    track_absence_grace_frames: int | None = None
    dwell_threshold_sec: float | None = None


class ZoneJobRequest(BaseModel):
    video_id: str
    zone_id: str
    config: ZoneJobConfig | None = None


class JobStatusOut(BaseModel):
    job_id: str
    kind: str
    status: str
    progress: float
    frames_processed: int | None = None
    total_frames: int | None = None
    processing_fps: float | None = None
    elapsed_sec: float | None = None
    eta_sec: float | None = None
    error: str | None = None
    summary: dict | None = None


class ReferenceUploadOut(BaseModel):
    reference_set_id: str
    photo_count: int


class PersonIdModuleRequest(BaseModel):
    reference_set_id: str
    config: dict | None = None


class AnprModuleRequest(BaseModel):
    target_plate: str | None = None
    config: dict | None = None


class BehaviorModuleRequest(BaseModel):
    config: dict | None = None


class LowlightModuleRequest(BaseModel):
    config: dict | None = None


class CombinedJobRequest(BaseModel):
    video_id: str
    person_id: PersonIdModuleRequest | None = None
    anpr: AnprModuleRequest | None = None
    zone_ids: list[str] = []
    behavior: BehaviorModuleRequest | None = None
    lowlight: LowlightModuleRequest | None = None


class PlateSearchRequest(BaseModel):
    video_id: str
    plate: str
    config: dict | None = None


class EvidenceItemOut(BaseModel):
    filename: str
    track_id: int | None = None
    event_type: str | None = None
    frame_index: int | None = None


class SystemStatusOut(BaseModel):
    device: str
    ocr_available: bool
    ocr_status: dict
    models_present: dict[str, bool]
    active_jobs: int
    total_jobs: int
