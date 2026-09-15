import { CloudFog } from "lucide-react";
import type { DehazeSummary } from "../../api/types";

export function DehazeSummaryCard({ summary }: { summary: DehazeSummary }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      <Stat label="Haze Detected" value={summary.haze_detected ? "Yes" : "No"} accent={summary.haze_detected} />
      <Stat label="Frames Dehazed" value={String(summary.dehazed_frames)} />
      <Stat label="Coverage" value={`${summary.dehazed_percentage.toFixed(1)}%`} />
      {!summary.dehazing_applied && (
        <div className="col-span-2 flex items-center gap-2 text-[11.5px] text-text-tertiary sm:col-span-3">
          <CloudFog size={13} /> This footage had no meaningful haze/mist — no dehazing was necessary.
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, accent, mono = true }: { label: string; value: string; accent?: boolean; mono?: boolean }) {
  return (
    <div className="rounded-md border border-border-1 bg-bg-3 px-3 py-2.5">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-text-tertiary">{label}</div>
      <div className={`mt-0.5 ${mono ? "font-mono" : ""} text-[13.5px] font-semibold ${accent ? "text-accent-blue" : "text-text-primary"}`}>{value}</div>
    </div>
  );
}
