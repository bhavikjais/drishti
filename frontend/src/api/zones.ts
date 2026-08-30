import { api } from "./client";
import type { Zone, ZoneCreateRequest, ZoneUpdateRequest } from "./types";

export function createZone(req: ZoneCreateRequest): Promise<Zone> {
  return api.post<Zone>("/api/zones", req);
}

export function getZone(zoneId: string): Promise<Zone> {
  return api.get<Zone>(`/api/zones/${encodeURIComponent(zoneId)}`);
}

export function updateZone(zoneId: string, req: ZoneUpdateRequest): Promise<Zone> {
  return api.put<Zone>(`/api/zones/${encodeURIComponent(zoneId)}`, req);
}
