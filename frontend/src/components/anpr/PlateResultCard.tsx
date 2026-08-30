import { CheckCircle2, ImageIcon, PlayCircle, XCircle } from "lucide-react";
import { formatConfidence, formatTimestamp } from "../../lib/format";
import type { AnprTarget } from "../../api/types";

export function PlateResultCard({
  target,
  searchedPlate,
  onJumpToVideo,
  onViewEvidence,
}: {
  target: AnprTarget;
  searchedPlate: string | null;
  onJumpToVideo?: () => void;
  onViewEvidence?: () => void;
}) {
  if (!target.found) {
    return (
      <div className="rounded-lg border border-border-2 bg-bg-3 px-5 py-6 text-center">
        <XCircle size={30} className="mx-auto mb-2 text-text-tertiary" />
        <div className="text-[15px] font-bold tracking-wide text-text-secondary">NOT FOUND</div>
        <p className="mx-auto mt-2 max-w-sm text-[12px] text-text-tertiary">
          No confirmed observation of {searchedPlate ? <span className="font-mono">{searchedPlate}</span> : "this plate"} was found in the analyzed video.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-accent-green/35 bg-accent-green/10 px-5 py-5">
      <div className="mb-3 flex items-center gap-2">
        <CheckCircle2 size={20} className="text-accent-green" />
        <span className="text-[14px] font-bold tracking-wide text-accent-green">FOUND</span>
      </div>
      <div className="mb-4 font-mono text-[22px] font-bold tracking-widest text-text-primary">{target.plate_text}</div>
      <div className="grid grid-cols-2 gap-3 text-[12.5px] sm:grid-cols-4">
        <Field label="Track" value={`#${target.track_id}`} />
        <Field label="Confidence" value={formatConfidence(target.match_confidence)} />
        <Field label="First Seen" value={formatTimestamp(target.first_seen_sec)} />
        <Field label="Last Seen" value={formatTimestamp(target.last_seen_sec)} />
      </div>
      <div className="mt-4 flex gap-2">
        {onViewEvidence && (
          <button onClick={onViewEvidence} className="inline-flex items-center gap-1.5 rounded border border-border-2 bg-bg-3 px-3 py-1.5 text-[11.5px] font-semibold text-text-secondary hover:bg-bg-4">
            <ImageIcon size={13} /> View Evidence
          </button>
        )}
        {onJumpToVideo && (
          <button onClick={onJumpToVideo} className="inline-flex items-center gap-1.5 rounded bg-accent-blue px-3 py-1.5 text-[11.5px] font-semibold text-[#051020] hover:bg-[#59aeff]">
            <PlayCircle size={13} /> Jump to Video
          </button>
        )}
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
