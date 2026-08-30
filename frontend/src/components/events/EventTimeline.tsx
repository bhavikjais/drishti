import { eventMeta } from "../../lib/eventMeta";
import { formatTimestamp } from "../../lib/format";
import type { BwEvent } from "../../api/types";

const borderBySeverity: Record<string, string> = {
  red: "border-l-accent-red",
  amber: "border-l-accent-amber",
  green: "border-l-accent-green",
  blue: "border-l-accent-blue",
  neutral: "border-l-border-2",
};

function eventDetails(ev: BwEvent): string | null {
  const d = ev.data || {};
  if (typeof d.confidence === "number") return `${(d.confidence as number).toFixed(1)}%`;
  if (typeof d.text === "string") return d.text as string;
  if (typeof d.duration_sec === "number") return `${(d.duration_sec as number).toFixed(1)}s`;
  if (typeof d.dwell_duration_sec === "number") return `dwell ${(d.dwell_duration_sec as number).toFixed(1)}s`;
  if (typeof d.trigger_behavior === "string") return d.trigger_behavior as string;
  return null;
}

export function EventTimeline({
  events,
  selectedId,
  onSelect,
  emptyLabel = "No events yet",
}: {
  events: BwEvent[];
  selectedId?: string | null;
  onSelect?: (ev: BwEvent) => void;
  emptyLabel?: string;
}) {
  if (events.length === 0) {
    return <div className="py-8 text-center text-[12.5px] text-text-tertiary">{emptyLabel}</div>;
  }

  return (
    <div className="flex flex-col gap-1">
      {events.map((ev, i) => {
        const meta = eventMeta(ev.type);
        const Icon = meta.icon;
        const id = ev.event_id ?? `${ev.type}-${ev.frame_index}-${i}`;
        const isSelected = selectedId === id;
        const details = eventDetails(ev);
        return (
          <button
            key={id}
            onClick={() => onSelect?.(ev)}
            className={`flex items-center gap-3 rounded-r border-l-2 px-3 py-2.5 text-left transition-colors ${borderBySeverity[meta.severity]} ${
              isSelected ? "bg-accent-blue/10" : "hover:bg-bg-3"
            }`}
          >
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded border border-border-1 bg-bg-3 text-text-secondary">
              <Icon size={14} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[12.5px] font-semibold text-text-primary">{meta.label}</div>
              <div className="mt-0.5 flex flex-wrap gap-x-2 text-[11px] text-text-tertiary">
                {ev.track_id != null && <span>Track #{ev.track_id}</span>}
                {ev.zone && <span className="truncate">Zone</span>}
                {details && <span className="truncate">{details}</span>}
              </div>
            </div>
            <div className="shrink-0 font-mono text-[11px] text-text-secondary">{formatTimestamp(ev.timestamp_sec)}</div>
          </button>
        );
      })}
    </div>
  );
}
