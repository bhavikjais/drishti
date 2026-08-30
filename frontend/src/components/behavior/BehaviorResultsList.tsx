import { eventMeta } from "../../lib/eventMeta";
import { formatTimestamp, titleCase } from "../../lib/format";
import type { BwEvent } from "../../api/types";

const BEHAVIOR_TYPES = new Set([
  "LOITERING",
  "SUDDEN_DIRECTION_CHANGE",
  "ABNORMAL_SPEED",
  "REPEATED_BACK_AND_FORTH",
  "TARGET_BEHAVIOR_ALERT",
]);

function detailLine(ev: BwEvent): string {
  const d = ev.data || {};
  if (ev.type === "LOITERING" && typeof d.duration_sec === "number") return `Duration ${(d.duration_sec as number).toFixed(1)}s`;
  if (ev.type === "TARGET_BEHAVIOR_ALERT" && typeof d.trigger_behavior === "string") return `Triggered by ${titleCase(d.trigger_behavior as string)}`;
  if (ev.type === "ABNORMAL_SPEED" && typeof d.speed_px_per_sec === "number") return `${(d.speed_px_per_sec as number).toFixed(0)} px/s (${d.reason})`;
  if (ev.type === "SUDDEN_DIRECTION_CHANGE" && typeof d.delta_deg === "number") return `${(d.delta_deg as number).toFixed(0)}° turn`;
  if (ev.type === "REPEATED_BACK_AND_FORTH" && typeof d.reversal_count === "number") return `${d.reversal_count} reversals`;
  return formatTimestamp(ev.timestamp_sec);
}

export function BehaviorResultsList({ events }: { events: BwEvent[] }) {
  const behaviorEvents = events.filter((e) => BEHAVIOR_TYPES.has(e.type));
  if (behaviorEvents.length === 0) {
    return <div className="py-6 text-center text-[12.5px] text-text-tertiary">No behavioral alerts detected</div>;
  }
  return (
    <div className="flex flex-col gap-2">
      {behaviorEvents.map((ev, i) => {
        const meta = eventMeta(ev.type);
        const Icon = meta.icon;
        const isTarget = ev.type === "TARGET_BEHAVIOR_ALERT";
        return (
          <div
            key={ev.event_id ?? i}
            className={`flex items-center gap-3 rounded-md border px-3.5 py-3 ${isTarget ? "border-accent-red/35 bg-accent-red/10" : "border-border-1 bg-bg-3"}`}
          >
            <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded ${isTarget ? "text-accent-red" : "text-accent-amber"}`}>
              <Icon size={16} />
            </div>
            <div className="min-w-0 flex-1">
              <div className={`text-[12.5px] font-bold ${isTarget ? "text-accent-red" : "text-text-primary"}`}>{meta.label.toUpperCase()}</div>
              <div className="mt-0.5 text-[11.5px] text-text-tertiary">
                Track #{ev.track_id} · {detailLine(ev)}
              </div>
            </div>
            <div className="shrink-0 font-mono text-[11px] text-text-secondary">{formatTimestamp(ev.timestamp_sec)}</div>
          </div>
        );
      })}
    </div>
  );
}
