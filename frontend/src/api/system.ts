import { api } from "./client";
import type { SystemStatus } from "./types";

export function getSystemStatus(): Promise<SystemStatus> {
  return api.get<SystemStatus>("/api/system/status");
}
