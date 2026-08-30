import { Crosshair } from "lucide-react";
import { formatDuration, formatTimestamp } from "../../lib/format";
import type { BwEvent, PersonIdSummary } from "../../api/types";

export function TargetCard({ summary, events }: { summary: PersonIdSummary; events: BwEvent[] }) {
  if (!summary.confirmed) {
    return (
      <div className="rounded-lg border border-border-2 bg-bg-3 px-5 py-6 text-center">
        <Crosshair size={26} className="mx-auto mb-2 text-text-tertiary" />
        <div className="text-[13.5px] font-bold text-text-secondary">TARGET NOT IDENTIFIED</div>
        <p className="mt-1 text-[11.5px] text-text-tertiary">No confirmed match against the uploaded reference photos was found in this video.</p>
      </div>
    );
  }

  const confirmedEvent = events.find((e) => e.type === "TARGET_CONFIRMED" && e.track_id === summary.target_track_id);
  const similarity = typeof confirmedEvent?.data?.similarity === "number" ? (confirmedEvent.data.similarity as number) * 100 : null;

  return (
    <div className="rounded-lg border border-accent-red/35 bg-accent-red/10 px-5 py-5">
      <div className="mb-3 flex items-center gap-2">
        <Crosshair size={18} className="text-accent-red" />
        <span className="text-[13px] font-bold tracking-wide text-accent-red">TARGET PERSON</span>
      </div>
      <div className="mb-4 font-mono text-[26px] font-bold text-text-primary">#{summary.target_track_id}</div>
      <div className="grid grid-cols-2 gap-3 text-[12.5px]">
        <Field label="Confidence" value={similarity != null ? `${similarity.toFixed(1)}%` : "—"} />
        <Field label="Frames Tracked" value={String(summary.visible_frame_count)} />
        <Field label="First Detected" value={formatTimestamp(summary.first_seen_sec)} />
        <Field label="Last Detected" value={formatTimestamp(summary.last_seen_sec)} />
      </div>
      <div className="mt-3 border-t border-accent-red/20 pt-3 text-[11.5px] text-text-tertiary">
        Visible for {formatDuration(summary.visible_duration_sec)} · {summary.reference_usable_count} reference photo{summary.reference_usable_count === 1 ? "" : "s"} used
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-wide text-text-tertiary">{label}</div>
      <div className="mt-0.5 font-mono font-semibold text-text-primary">{value}</div>
    </div>
  );
}
