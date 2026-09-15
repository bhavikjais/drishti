import { useEffect, useRef, useState } from "react";
import { getJob } from "../api/jobs";
import { ApiError } from "../api/client";
import type { JobStatusOut } from "../api/types";

const TERMINAL: JobStatusOut["status"][] = ["done", "failed", "cancelled"];

/** Polls GET /api/jobs/{id} at a sensible interval while the job is
 * pending/running, and stops automatically once it reaches a terminal
 * state (done/failed/cancelled) - never polls a finished job forever.
 * Cleans up its timer on unmount or when jobId changes. */
export function useJobPolling(jobId: string | undefined, intervalMs = 1500) {
  const [job, setJob] = useState<JobStatusOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    setJob(null);
    setError(null);
    if (!jobId) return;
    let cancelled = false;

    const tick = async () => {
      try {
        const result = await getJob(jobId);
        if (cancelled) return;
        setJob(result);
        setError(null);
        if (!TERMINAL.includes(result.status)) {
          timerRef.current = window.setTimeout(tick, intervalMs);
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Failed to reach Drishti API");
        timerRef.current = window.setTimeout(tick, intervalMs * 2);
      }
    };
    tick();

    return () => {
      cancelled = true;
      if (timerRef.current != null) window.clearTimeout(timerRef.current);
    };
  }, [jobId, intervalMs]);

  return { job, error, isTerminal: job ? TERMINAL.includes(job.status) : false };
}
