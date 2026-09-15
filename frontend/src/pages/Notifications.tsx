import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, Image as ImageIcon } from "lucide-react";
import { getJobEvents, getJobEvidence, jobEvidenceFileUrl, listJobs } from "../api/jobs";
import type { BwEvent, JobStatusOut } from "../api/types";
import { PageBody, PageHeader } from "../components/layout/AppLayout";
import { Panel } from "../components/common/Panel";
import { EmptyState, ErrorState, LoadingBlock } from "../components/common/States";
import { eventFeature, eventMeta, isNotifiable, FEATURE_LABELS, type Feature } from "../lib/eventMeta";
import { formatTimestamp } from "../lib/format";
import { useApi } from "../hooks/useApi";

const MAX_JOBS_SCANNED = 25;

interface NotificationRow {
  job: JobStatusOut;
  event: BwEvent;
  evidenceFilename: string | null;
}

const borderBySeverity: Record<string, string> = {
  red: "border-l-accent-red",
  amber: "border-l-accent-amber",
  green: "border-l-accent-green",
  blue: "border-l-accent-blue",
  neutral: "border-l-border-2",
};

// Cross-job feed: scans the N most recently finished jobs and pulls every
// notification-worthy event out of each, same isNotifiable()/eventFeature()
// rules as the per-job panel on the Results page (see NotificationsPanel.tsx)
// - this is the "all jobs" superset of that, not a different curation.
// Client-side aggregation (listJobs + per-job events/evidence), same pattern
// already used by pages/Events.tsx - no new backend endpoint needed.
async function loadAllNotifications(): Promise<NotificationRow[]> {
  const jobs = await listJobs();
  const done = jobs.filter((j) => j.status === "done").slice(0, MAX_JOBS_SCANNED);
  const perJob = await Promise.all(
    done.map(async (job): Promise<NotificationRow[]> => {
      try {
        const [events, evidence] = await Promise.all([getJobEvents(job.job_id), getJobEvidence(job.job_id)]);
        const evidenceByKey = new Map(
          evidence.filter((e) => e.event_type).map((e) => [`${e.track_id}_${e.event_type}_${e.frame_index}`, e.filename]),
        );
        return events
          .filter((ev) => isNotifiable(ev.type))
          .map((event) => ({ job, event, evidenceFilename: evidenceByKey.get(`${event.track_id}_${event.type}_${event.frame_index}`) ?? null }));
      } catch {
        return [];
      }
    }),
  );
  return perJob.flat().sort((a, b) => b.event.timestamp_sec - a.event.timestamp_sec);
}

export function Notifications() {
  const { status, data, error, refetch } = useApi(loadAllNotifications);
  const navigate = useNavigate();
  const [activeFeatures, setActiveFeatures] = useState<Set<Feature>>(new Set());

  const presentFeatures = useMemo(() => {
    const set = new Set<Feature>();
    for (const row of data ?? []) set.add(eventFeature(row.event.type));
    return Array.from(set);
  }, [data]);

  const visible = useMemo(() => {
    if (!data) return [];
    return activeFeatures.size === 0 ? data : data.filter((row) => activeFeatures.has(eventFeature(row.event.type)));
  }, [data, activeFeatures]);

  function toggleFeature(f: Feature) {
    setActiveFeatures((prev) => {
      const next = new Set(prev);
      if (next.has(f)) next.delete(f);
      else next.add(f);
      return next;
    });
  }

  return (
    <>
      <PageHeader title="Notifications" subtitle="Alert-worthy events across every analysis job, with tracked-object snapshots" />
      <PageBody>
        {presentFeatures.length > 1 && (
          <Panel className="mb-4" tight>
            <div className="flex flex-wrap gap-1.5 p-2">
              <button
                onClick={() => setActiveFeatures(new Set())}
                className={`rounded-full border px-3 py-1.5 text-[11.5px] font-semibold transition-colors ${
                  activeFeatures.size === 0 ? "border-accent-blue/40 bg-accent-blue/12 text-accent-blue" : "border-border-2 text-text-tertiary hover:border-border-strong"
                }`}
              >
                All ({data?.length ?? 0})
              </button>
              {presentFeatures.map((f) => {
                const count = (data ?? []).filter((row) => eventFeature(row.event.type) === f).length;
                const active = activeFeatures.has(f);
                return (
                  <button
                    key={f}
                    onClick={() => toggleFeature(f)}
                    className={`rounded-full border px-3 py-1.5 text-[11.5px] font-semibold transition-colors ${
                      active ? "border-accent-blue/40 bg-accent-blue/12 text-accent-blue" : "border-border-2 text-text-tertiary hover:border-border-strong"
                    }`}
                  >
                    {FEATURE_LABELS[f]} ({count})
                  </button>
                );
              })}
            </div>
          </Panel>
        )}

        <Panel>
          {status === "loading" && <LoadingBlock label="Loading notifications…" />}
          {status === "error" && <ErrorState message={error} onRetry={refetch} />}
          {status === "success" && visible.length === 0 && (
            <EmptyState
              icon={Bell}
              title="No notifications"
              description={data && data.length > 0 ? "No notifications match the current filter." : "Run an analysis to start generating alerts."}
            />
          )}
          {status === "success" && visible.length > 0 && (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(230px,1fr))] gap-3">
              {visible.map((row, i) => {
                const meta = eventMeta(row.event.type);
                const Icon = meta.icon;
                const eta = typeof row.event.data?.eta_sec === "number" ? (row.event.data.eta_sec as number) : null;
                return (
                  <button
                    key={`${row.job.job_id}-${row.event.event_id ?? i}`}
                    onClick={() => navigate(`/results/${row.job.job_id}`)}
                    className={`flex flex-col overflow-hidden rounded-md border-l-2 border border-border-1 bg-bg-3 text-left transition-colors hover:border-border-strong ${borderBySeverity[meta.severity]}`}
                  >
                    {row.evidenceFilename ? (
                      <img
                        src={jobEvidenceFileUrl(row.job.job_id, row.evidenceFilename)}
                        alt={meta.label}
                        loading="lazy"
                        className="h-[110px] w-full bg-bg-4 object-cover"
                      />
                    ) : (
                      <div className="flex h-[110px] w-full items-center justify-center bg-bg-4 text-text-disabled">
                        <ImageIcon size={22} />
                      </div>
                    )}
                    <div className="flex items-start gap-2 px-3 py-2.5">
                      <Icon size={14} className="mt-0.5 shrink-0 text-text-secondary" />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[12px] font-semibold text-text-primary">{meta.label}</div>
                        <div className="mt-0.5 flex flex-wrap gap-x-1.5 text-[10.5px] text-text-tertiary">
                          {row.event.track_id != null && <span>Track #{row.event.track_id}</span>}
                          {eta != null && <span>ETA {eta.toFixed(1)}s</span>}
                          {row.event.zone && <span className="truncate">{row.event.zone}</span>}
                          <span className="font-mono">{formatTimestamp(row.event.timestamp_sec)}</span>
                        </div>
                        <div className="mt-1 truncate font-mono text-[10px] text-text-disabled">Job {row.job.job_id.slice(0, 8)}</div>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </Panel>
      </PageBody>
    </>
  );
}
