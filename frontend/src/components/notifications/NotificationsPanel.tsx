import { useMemo, useState } from "react";
import { Bell, Image as ImageIcon } from "lucide-react";
import { eventFeature, eventMeta, isNotifiable, FEATURE_LABELS, type Feature } from "../../lib/eventMeta";
import { formatTimestamp } from "../../lib/format";
import { jobEvidenceFileUrl } from "../../api/jobs";
import type { BwEvent, EvidenceItem } from "../../api/types";

const borderBySeverity: Record<string, string> = {
  red: "border-l-accent-red",
  amber: "border-l-accent-amber",
  green: "border-l-accent-green",
  blue: "border-l-accent-blue",
  neutral: "border-l-border-2",
};

function evidenceKey(trackId: number | null, type: string, frameIndex: number | null): string {
  return `${trackId}_${type}_${frameIndex}`;
}

/** All notification-worthy events for this job, each paired with its
 * tracked-object snapshot when the backend captured one (see
 * orchestrator.py's save_evidence - matched here by the same
 * track_id/type/frame_index triple it names the file with), with a
 * feature-module filter since a run can have five modules firing events at
 * once. */
export function NotificationsPanel({
  jobId,
  events,
  evidence,
  selectedId,
  onSelect,
}: {
  jobId: string;
  events: BwEvent[];
  evidence: EvidenceItem[];
  selectedId?: string | null;
  onSelect?: (ev: BwEvent) => void;
}) {
  const [activeFeatures, setActiveFeatures] = useState<Set<Feature>>(new Set());

  const evidenceByKey = useMemo(() => {
    const map = new Map<string, EvidenceItem>();
    for (const item of evidence) {
      if (item.event_type) map.set(evidenceKey(item.track_id, item.event_type, item.frame_index), item);
    }
    return map;
  }, [evidence]);

  const notifications = useMemo(
    () => events.filter((ev) => isNotifiable(ev.type)).sort((a, b) => b.timestamp_sec - a.timestamp_sec),
    [events],
  );

  const presentFeatures = useMemo(() => {
    const set = new Set<Feature>();
    for (const ev of notifications) set.add(eventFeature(ev.type));
    return Array.from(set);
  }, [notifications]);

  const visible = useMemo(
    () => (activeFeatures.size === 0 ? notifications : notifications.filter((ev) => activeFeatures.has(eventFeature(ev.type)))),
    [notifications, activeFeatures],
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
    <div className="flex flex-col gap-3">
      {presentFeatures.length > 1 && (
        <div className="flex flex-wrap gap-1.5">
          <button
            onClick={() => setActiveFeatures(new Set())}
            className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold transition-colors ${
              activeFeatures.size === 0 ? "border-accent-blue/40 bg-accent-blue/12 text-accent-blue" : "border-border-2 text-text-tertiary hover:border-border-strong"
            }`}
          >
            All ({notifications.length})
          </button>
          {presentFeatures.map((f) => {
            const count = notifications.filter((ev) => eventFeature(ev.type) === f).length;
            const active = activeFeatures.has(f);
            return (
              <button
                key={f}
                onClick={() => toggleFeature(f)}
                className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                  active ? "border-accent-blue/40 bg-accent-blue/12 text-accent-blue" : "border-border-2 text-text-tertiary hover:border-border-strong"
                }`}
              >
                {FEATURE_LABELS[f]} ({count})
              </button>
            );
          })}
        </div>
      )}

      {visible.length === 0 ? (
        <div className="flex flex-col items-center gap-2 py-10 text-center text-text-tertiary">
          <Bell size={26} className="opacity-50" />
          <div className="text-[12.5px]">No notifications{activeFeatures.size > 0 ? " for this filter" : ""}</div>
        </div>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
          {visible.map((ev, i) => {
            const meta = eventMeta(ev.type);
            const Icon = meta.icon;
            const id = ev.event_id ?? `${ev.type}-${ev.frame_index}-${i}`;
            const image = evidenceByKey.get(evidenceKey(ev.track_id, ev.type, ev.frame_index));
            const eta = typeof ev.data?.eta_sec === "number" ? (ev.data.eta_sec as number) : null;

            return (
              <button
                key={id}
                onClick={() => onSelect?.(ev)}
                className={`flex flex-col overflow-hidden rounded-md border-l-2 border border-border-1 bg-bg-3 text-left transition-colors ${borderBySeverity[meta.severity]} ${
                  selectedId === id ? "bg-accent-blue/10" : "hover:border-border-strong"
                }`}
              >
                {image ? (
                  <img src={jobEvidenceFileUrl(jobId, image.filename)} alt={meta.label} loading="lazy" className="h-[110px] w-full bg-bg-4 object-cover" />
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
                      {ev.track_id != null && <span>Track #{ev.track_id}</span>}
                      {eta != null && <span>ETA {eta.toFixed(1)}s</span>}
                      {ev.zone && <span className="truncate">{ev.zone}</span>}
                      <span className="font-mono">{formatTimestamp(ev.timestamp_sec)}</span>
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
