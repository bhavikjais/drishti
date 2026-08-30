import { Sparkles } from "lucide-react";
import type { LowlightSummary } from "../../api/types";

const BACKEND_LABEL: Record<string, string> = { fast: "Fast CLAHE/Gamma", zero_dce: "Zero-DCE++" };

export function LowlightSummaryCard({ summary }: { summary: LowlightSummary }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Stat label="Low-Light Detected" value={summary.low_light_detected ? "Yes" : "No"} accent={summary.low_light_detected} />
      <Stat label="Frames Enhanced" value={String(summary.enhanced_frames)} />
      <Stat label="Coverage" value={`${summary.enhanced_percentage.toFixed(1)}%`} />
      <Stat label="Backend" value={BACKEND_LABEL[summary.backend] ?? summary.backend} mono={false} />
      {!summary.enhancement_applied && (
        <div className="col-span-2 flex items-center gap-2 text-[11.5px] text-text-tertiary sm:col-span-4">
          <Sparkles size={13} /> This footage was already well-lit — no enhancement was necessary.
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
