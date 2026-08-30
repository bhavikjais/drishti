import { useEffect, useState } from "react";
import { getJobEvents, listJobs } from "../api/jobs";
import type { BwEvent, JobStatusOut } from "../api/types";

export interface DashboardMetrics {
  videosAnalyzed: number;
  targetsIdentified: number;
  vehiclesDetected: number;
  platesRead: number;
  securityEvents: number;
}

/** Derived entirely from real job summaries already returned by GET
 * /api/jobs - no per-job event fetch here (would be N+1 requests against
 * every job ever run). "Security events" is therefore a meaningful-event
 * proxy (confirmed targets/plates + zone entries/exits/dwells + behavior
 * alerts) rather than a raw count of every low-level event type - documented
 * here rather than silently presented as something it isn't. */
function computeMetrics(jobs: JobStatusOut[]): DashboardMetrics {
  const done = jobs.filter((j) => j.status === "done");
  let targets = 0;
  let vehicles = 0;
  let plates = 0;
  let securityEvents = 0;

  for (const job of done) {
    const s = job.summary;
    if (!s) continue;
    if (s.person_id?.confirmed) {
      targets += 1;
      securityEvents += 1;
    }
    if (s.anpr) {
      vehicles += s.anpr.vehicles_detected;
      plates += s.anpr.detected_plates.length;
      securityEvents += s.anpr.detected_plates.filter((p) => p.confirmed).length;
    }
    if (s.zones) {
      for (const z of s.zones) securityEvents += z.entries + z.exits + z.dwell_events;
    }
    if (s.behavior) {
      securityEvents += Object.values(s.behavior.event_counts).reduce((a, b) => a + b, 0);
    }
  }

  return { videosAnalyzed: done.length, targetsIdentified: targets, vehiclesDetected: vehicles, platesRead: plates, securityEvents };
}

export interface DashboardData {
  loading: boolean;
  error: string | null;
  jobs: JobStatusOut[];
  metrics: DashboardMetrics;
  activeJob: JobStatusOut | null;
  recentEvents: { job: JobStatusOut; event: BwEvent }[];
}

const RECENT_EVENT_JOB_LIMIT = 3;
const RECENT_EVENT_COUNT = 8;

export function useDashboardData(): DashboardData & { refetch: () => void } {
  const [state, setState] = useState<Omit<DashboardData, "loading" | "error">>({
    jobs: [],
    metrics: { videosAnalyzed: 0, targetsIdentified: 0, vehiclesDetected: 0, platesRead: 0, securityEvents: 0 },
    activeJob: null,
    recentEvents: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const jobs = await listJobs();
        if (cancelled) return;
        const metrics = computeMetrics(jobs);
        const activeJob = jobs.find((j) => j.status === "pending" || j.status === "running") ?? null;

        const recentDone = jobs.filter((j) => j.status === "done").slice(0, RECENT_EVENT_JOB_LIMIT);
        const eventLists = await Promise.all(
          recentDone.map(async (job) => {
            try {
              const events = await getJobEvents(job.job_id);
              return events.map((event) => ({ job, event }));
            } catch {
              return [];
            }
          }),
        );
        if (cancelled) return;
        const recentEvents = eventLists
          .flat()
          .sort((a, b) => b.job.elapsed_sec! - a.job.elapsed_sec! || b.event.frame_index - a.event.frame_index)
          .slice(0, RECENT_EVENT_COUNT);

        setState({ jobs, metrics, activeJob, recentEvents });
        setError(null);
      } catch {
        if (!cancelled) setError("Failed to reach BorderWatch API");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tick]);

  return { ...state, loading, error, refetch: () => setTick((t) => t + 1) };
}
