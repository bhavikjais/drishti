import { api } from "./client";
import type { BwEvent, CombinedJobRequest, EvidenceItem, JobStatusOut, PlateSearchRequest } from "./types";

export function startCombinedJob(req: CombinedJobRequest): Promise<JobStatusOut> {
  return api.post<JobStatusOut>("/api/jobs", req);
}

export function searchPlate(req: PlateSearchRequest): Promise<JobStatusOut> {
  return api.post<JobStatusOut>("/api/anpr/search", req);
}

export function listJobs(): Promise<JobStatusOut[]> {
  return api.get<JobStatusOut[]>("/api/jobs");
}

export function getJob(jobId: string): Promise<JobStatusOut> {
  return api.get<JobStatusOut>(`/api/jobs/${encodeURIComponent(jobId)}`);
}

export function cancelJob(jobId: string): Promise<JobStatusOut> {
  return api.post<JobStatusOut>(`/api/jobs/${encodeURIComponent(jobId)}/cancel`);
}

export function getJobEvents(jobId: string): Promise<BwEvent[]> {
  return api.get<BwEvent[]>(`/api/jobs/${encodeURIComponent(jobId)}/events`);
}

export function getJobEvidence(jobId: string): Promise<EvidenceItem[]> {
  return api.get<EvidenceItem[]>(`/api/jobs/${encodeURIComponent(jobId)}/evidence`);
}

export function jobOutputUrl(jobId: string): string {
  return `/api/jobs/${encodeURIComponent(jobId)}/output`;
}

export function jobEvidenceFileUrl(jobId: string, filename: string): string {
  return `/api/jobs/${encodeURIComponent(jobId)}/evidence/${encodeURIComponent(filename)}`;
}
