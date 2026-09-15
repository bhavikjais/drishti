// Standalone app - no Vite dev proxy, so this talks to the FastAPI backend
// directly over the network (backend/app.py has CORS opened for this app's
// origin). Override with a .env.local (VITE_API_BASE=http://host:8000) to
// point this at a non-default backend without touching code.
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

// Where the main dashboard (frontend/) lives, for the "open in dashboard"
// link on each notification - that app owns video playback/results detail,
// this app deliberately doesn't reimplement it.
export const DASHBOARD_BASE = import.meta.env.VITE_DASHBOARD_BASE ?? "http://localhost:5173";

export class ApiError extends Error {}

async function request<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new ApiError(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export interface JobStatusOut {
  job_id: string;
  kind: string;
  status: string;
}

export interface BwEvent {
  event_id?: string;
  type: string;
  track_id: number | null;
  frame_index: number;
  timestamp_sec: number;
  zone?: string;
  data: Record<string, unknown>;
}

export interface EvidenceItem {
  filename: string;
  track_id: number | null;
  event_type: string | null;
  frame_index: number | null;
}

export function listJobs(): Promise<JobStatusOut[]> {
  return request<JobStatusOut[]>("/api/jobs");
}

export function getJobEvents(jobId: string): Promise<BwEvent[]> {
  return request<BwEvent[]>(`/api/jobs/${encodeURIComponent(jobId)}/events`);
}

export function getJobEvidence(jobId: string): Promise<EvidenceItem[]> {
  return request<EvidenceItem[]>(`/api/jobs/${encodeURIComponent(jobId)}/evidence`);
}

export function jobEvidenceFileUrl(jobId: string, filename: string): string {
  return `${API_BASE}/api/jobs/${encodeURIComponent(jobId)}/evidence/${encodeURIComponent(filename)}`;
}
