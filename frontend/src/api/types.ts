// Types mirror backend/api/schemas.py and backend/orchestrator.py's summary
// shapes exactly. If the backend adds/renames a field, update here - never
// invent fields that aren't actually returned.

export interface VideoInfo {
  fps: number;
  width: number;
  height: number;
  frame_count: number;
  duration_sec: number;
}

export interface VideoUpload {
  video_id: string;
  filename: string;
  video_info: VideoInfo;
}

export type ZoneShape = "rectangle" | "polygon";

export interface Zone {
  zone_id: string;
  video_id: string;
  label: string;
  shape: ZoneShape;
  points: [number, number][];
}

export interface ReferenceUpload {
  reference_set_id: string;
  photo_count: number;
}

export type JobStatus = "pending" | "running" | "done" | "failed" | "cancelled";

export interface JobStatusOut {
  job_id: string;
  kind: string;
  status: JobStatus;
  progress: number;
  frames_processed: number | null;
  total_frames: number | null;
  processing_fps: number | null;
  elapsed_sec: number | null;
  eta_sec: number | null;
  error: string | null;
  summary: JobSummary | null;
}

export interface PersonIdSummary {
  confirmed: boolean;
  target_track_id: number | null;
  first_seen_sec: number | null;
  last_seen_sec: number | null;
  visible_duration_sec: number;
  visible_frame_count: number;
  reference_usable_count: number;
  min_reference_votes_used: number;
  snapshot_path: string | null;
}

export interface DetectedPlate {
  track_id: number;
  text: string;
  mean_confidence: number;
  observation_count: number;
  confirmed: boolean;
}

export interface AnprTarget {
  found: boolean;
  track_id: number | null;
  plate_text: string | null;
  match_confidence: number | null;
  first_seen_sec: number | null;
  last_seen_sec: number | null;
  visible_duration_sec: number;
  visible_frame_count: number;
}

export interface AnprSummary {
  mode: "automatic" | "search";
  searched_plate: string | null;
  target: AnprTarget | null;
  detected_plates: DetectedPlate[];
  vehicles_detected: number;
  ocr_status: Record<string, unknown>;
}

export interface ZoneSummary {
  zone_id: string;
  label: string;
  entries: number;
  exits: number;
  dwell_events: number;
}

export interface BehaviorSummary {
  event_counts: Record<string, number>;
  tracks_observed: number;
}

export interface LowlightSummary {
  low_light_detected: boolean;
  enhancement_applied: boolean;
  backend: string;
  low_light_frames: number;
  enhanced_frames: number;
  enhanced_percentage: number;
}

export interface JobSummary {
  // combined-job fields
  modules_run?: string[];
  codec_used?: string;
  browser_playable?: boolean;
  video_info?: VideoInfo;
  person_id?: PersonIdSummary | null;
  anpr?: AnprSummary | null;
  zones?: ZoneSummary[] | null;
  behavior?: BehaviorSummary | null;
  lowlight?: LowlightSummary | null;
  // legacy zone-only job fields (POST /api/zone-jobs)
  zone_id?: string;
  tracks_observed?: number;
  entries?: number;
  exits?: number;
  dwell_events?: number;
}

export interface BwEvent {
  event_id?: string;
  type: string;
  track_id: number | null;
  frame_index: number;
  timestamp_sec: number;
  zone?: string;
  plate?: string;
  confidence?: number;
  evidence_path?: string | null;
  data: Record<string, unknown>;
}

export interface EvidenceItem {
  filename: string;
  track_id: number | null;
  event_type: string | null;
  frame_index: number | null;
}

export interface SystemStatus {
  device: string;
  ocr_available: boolean;
  ocr_status: Record<string, unknown>;
  models_present: Record<string, boolean>;
  active_jobs: number;
  total_jobs: number;
}

// --- request payloads ---

export interface PersonIdModuleRequest {
  reference_set_id: string;
  config?: Record<string, number> | null;
}

export interface AnprModuleRequest {
  target_plate?: string | null;
  config?: Record<string, number> | null;
}

export interface BehaviorModuleRequest {
  config?: Record<string, number> | null;
}

export interface LowlightModuleRequest {
  config?: Record<string, number | string | boolean> | null;
}

export interface CombinedJobRequest {
  video_id: string;
  person_id?: PersonIdModuleRequest | null;
  anpr?: AnprModuleRequest | null;
  zone_ids?: string[];
  behavior?: BehaviorModuleRequest | null;
  lowlight?: LowlightModuleRequest | null;
}

export interface PlateSearchRequest {
  video_id: string;
  plate: string;
  config?: Record<string, number> | null;
}

export interface ZoneCreateRequest {
  video_id: string;
  shape: ZoneShape;
  points: [number, number][];
  label?: string;
}

export interface ZoneUpdateRequest {
  shape?: ZoneShape | null;
  points?: [number, number][] | null;
  label?: string | null;
}
