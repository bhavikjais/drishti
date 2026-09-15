import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Bell, BellOff, ExternalLink, Image as ImageIcon, Radio } from "lucide-react";
import { DASHBOARD_BASE, getJobEvents, getJobEvidence, jobEvidenceFileUrl, listJobs, type BwEvent, type JobStatusOut } from "./lib/api";
import { eventFeature, eventMeta, isNotifiable, FEATURE_LABELS, type Feature } from "./lib/eventMeta";
import { formatTimestamp } from "./lib/format";
import { playSiren } from "./lib/siren";

const POLL_INTERVAL_MS = 5000;
const MAX_JOBS_SCANNED = 25;

interface Row {
  id: string; // stable across polls - used to detect genuinely new alerts
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

async function fetchRows(): Promise<Row[]> {
  const jobs = await listJobs();
  const done = jobs.filter((j) => j.status === "done").slice(0, MAX_JOBS_SCANNED);
  const perJob = await Promise.all(
    done.map(async (job): Promise<Row[]> => {
      try {
        const [events, evidence] = await Promise.all([getJobEvents(job.job_id), getJobEvidence(job.job_id)]);
        const evidenceByKey = new Map(
          evidence.filter((e) => e.event_type).map((e) => [`${e.track_id}_${e.event_type}_${e.frame_index}`, e.filename]),
        );
        return events
          .filter((ev) => isNotifiable(ev.type))
          .map((event) => ({
            id: `${job.job_id}:${event.event_id ?? `${event.type}-${event.frame_index}`}`,
            job,
            event,
            evidenceFilename: evidenceByKey.get(`${event.track_id}_${event.type}_${event.frame_index}`) ?? null,
          }));
      } catch {
        return [];
      }
    }),
  );
  return perJob.flat().sort((a, b) => b.event.timestamp_sec - a.event.timestamp_sec);
}

export default function App() {
  const [rows, setRows] = useState<Row[]>([]);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [lastPolled, setLastPolled] = useState<Date | null>(null);
  const [muted, setMuted] = useState(false);
  const [desktopEnabled, setDesktopEnabled] = useState(false);
  const [activeFeatures, setActiveFeatures] = useState<Set<Feature>>(new Set());
  const seenIdsRef = useRef<Set<string> | null>(null); // null until the first poll establishes a baseline

  const poll = useCallback(async () => {
    try {
      const fresh = await fetchRows();
      const freshIds = new Set(fresh.map((r) => r.id));

      if (seenIdsRef.current === null) {
        // First load: seed the baseline silently - opening this app shouldn't
        // blast the siren for every alert already in history.
        seenIdsRef.current = freshIds;
      } else {
        const newOnes = fresh.filter((r) => !seenIdsRef.current!.has(r.id));
        if (newOnes.length > 0) {
          if (!muted) playSiren();
          if (desktopEnabled && "Notification" in window && Notification.permission === "granted") {
            for (const r of newOnes.slice(0, 5)) {
              const meta = eventMeta(r.event.type);
              new Notification(meta.label, {
                body: `${r.event.track_id != null ? `Track #${r.event.track_id} · ` : ""}Job ${r.job.job_id.slice(0, 8)}`,
                tag: r.id,
              });
            }
          }
        }
        seenIdsRef.current = freshIds;
      }

      setRows(fresh);
      setLoadState("ready");
      setLastPolled(new Date());
    } catch {
      setLoadState("error");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [muted, desktopEnabled]);

  useEffect(() => {
    poll();
    const id = setInterval(poll, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [poll]);

  async function enableDesktopAlerts() {
    if (!("Notification" in window)) return;
    const perm = await Notification.requestPermission();
    setDesktopEnabled(perm === "granted");
  }

  const presentFeatures = useMemo(() => {
    const set = new Set<Feature>();
    for (const r of rows) set.add(eventFeature(r.event.type));
    return Array.from(set);
  }, [rows]);

  const visible = useMemo(
    () => (activeFeatures.size === 0 ? rows : rows.filter((r) => activeFeatures.has(eventFeature(r.event.type)))),
    [rows, activeFeatures],
  );

  function toggleFeature(f: Feature) {
    setActiveFeatures((prev) => {
      const next = new Set(prev);
      if (next.has(f)) next.delete(f);
      else next.add(f);
      return next;
    });
  }

  return (
    <div className="mx-auto max-w-[1100px] px-4 py-6 sm:px-6">
      <header className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-border-1 pb-4">
        <div>
          <div className="flex items-center gap-2 text-lg font-bold tracking-wide text-text-primary">
            <span className="h-2 w-2 shrink-0 rounded-full bg-accent-blue shadow-[0_0_8px_var(--color-accent-blue)]" />
            DRISHTI NOTIFICATIONS
          </div>
          <div className="mt-1 pl-4 text-[11px] tracking-[1px] text-text-tertiary">
            Standalone alert feed · connected to {new URL(import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000").host}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill loadState={loadState} lastPolled={lastPolled} />
          <button
            onClick={() => setMuted((m) => !m)}
            title={muted ? "Unmute alarm" : "Mute alarm"}
            className="flex items-center gap-1.5 rounded border border-border-2 bg-bg-3 px-2.5 py-1.5 text-[11.5px] font-semibold text-text-secondary transition-colors hover:border-border-strong"
          >
            {muted ? <BellOff size={14} /> : <Bell size={14} />}
            {muted ? "Muted" : "Sound On"}
          </button>
          {!desktopEnabled && "Notification" in window && (
            <button
              onClick={enableDesktopAlerts}
              className="rounded border border-accent-blue/40 bg-accent-blue/10 px-2.5 py-1.5 text-[11.5px] font-semibold text-accent-blue transition-colors hover:bg-accent-blue/20"
            >
              Enable Desktop Alerts
            </button>
          )}
        </div>
      </header>

      {presentFeatures.length > 1 && (
        <div className="mb-4 flex flex-wrap gap-1.5">
          <button
            onClick={() => setActiveFeatures(new Set())}
            className={`rounded-full border px-3 py-1.5 text-[11.5px] font-semibold transition-colors ${
              activeFeatures.size === 0 ? "border-accent-blue/40 bg-accent-blue/12 text-accent-blue" : "border-border-2 text-text-tertiary hover:border-border-strong"
            }`}
          >
            All ({rows.length})
          </button>
          {presentFeatures.map((f) => {
            const count = rows.filter((r) => eventFeature(r.event.type) === f).length;
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
      )}

      {loadState === "loading" && <div className="py-16 text-center text-[12.5px] text-text-tertiary">Loading notifications…</div>}
      {loadState === "error" && (
        <div className="py-16 text-center text-[12.5px] text-accent-red">
          Couldn't reach the backend. Confirm it's running and CORS allows this app's origin.
        </div>
      )}
      {loadState === "ready" && visible.length === 0 && (
        <div className="flex flex-col items-center gap-2 py-16 text-center text-text-tertiary">
          <Bell size={26} className="opacity-50" />
          <div className="text-[12.5px]">No notifications{activeFeatures.size > 0 ? " for this filter" : " yet"}</div>
        </div>
      )}
      {loadState === "ready" && visible.length > 0 && (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(230px,1fr))] gap-3">
          {visible.map((row) => {
            const meta = eventMeta(row.event.type);
            const Icon = meta.icon;
            const eta = typeof row.event.data?.eta_sec === "number" ? (row.event.data.eta_sec as number) : null;
            return (
              <a
                key={row.id}
                href={`${DASHBOARD_BASE}/results/${row.job.job_id}`}
                target="_blank"
                rel="noreferrer"
                className={`flex flex-col overflow-hidden rounded-md border-l-2 border border-border-1 bg-bg-3 text-left transition-colors hover:border-border-strong ${borderBySeverity[meta.severity]}`}
              >
                {row.evidenceFilename ? (
                  <img src={jobEvidenceFileUrl(row.job.job_id, row.evidenceFilename)} alt={meta.label} loading="lazy" className="h-[110px] w-full bg-bg-4 object-cover" />
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
                    <div className="mt-1 flex items-center gap-1 truncate font-mono text-[10px] text-text-disabled">
                      Job {row.job.job_id.slice(0, 8)} <ExternalLink size={10} />
                    </div>
                  </div>
                </div>
              </a>
            );
          })}
        </div>
      )}
    </div>
  );
}

function StatusPill({ loadState, lastPolled }: { loadState: "loading" | "ready" | "error"; lastPolled: Date | null }) {
  const color = loadState === "ready" ? "bg-accent-green" : loadState === "error" ? "bg-accent-red" : "bg-accent-amber";
  const label = loadState === "ready" ? `Live · polled ${lastPolled ? lastPolled.toLocaleTimeString() : ""}` : loadState === "error" ? "Disconnected" : "Connecting…";
  return (
    <div className="flex items-center gap-1.5 rounded-full border border-border-2 bg-bg-3 px-2.5 py-1.5 text-[11px] font-semibold text-text-secondary">
      <Radio size={12} className="opacity-70" />
      <span className={`h-[6px] w-[6px] rounded-full ${color}`} />
      {label}
    </div>
  );
}
