import { Image as ImageIcon } from "lucide-react";
import { jobEvidenceFileUrl } from "../../api/jobs";
import { titleCase } from "../../lib/format";
import type { EvidenceItem } from "../../api/types";

export function EvidenceGrid({
  jobId,
  items,
  onOpen,
}: {
  jobId: string;
  items: EvidenceItem[];
  onOpen?: (item: EvidenceItem) => void;
}) {
  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-10 text-center text-text-tertiary">
        <ImageIcon size={28} className="opacity-50" />
        <div className="text-[12.5px]">No evidence captured for this analysis</div>
      </div>
    );
  }
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3">
      {items.map((item) => (
        <button
          key={item.filename}
          onClick={() => onOpen?.(item)}
          className="overflow-hidden rounded-md border border-border-1 bg-bg-3 text-left transition-colors hover:border-border-strong"
        >
          <img src={jobEvidenceFileUrl(jobId, item.filename)} alt={item.event_type ?? "evidence"} loading="lazy" className="h-[100px] w-full bg-bg-4 object-cover" />
          <div className="px-3 py-2">
            <div className="truncate text-[11px] font-semibold text-text-primary">{item.event_type ? titleCase(item.event_type) : "Evidence"}</div>
            <div className="mt-0.5 text-[10.5px] text-text-tertiary">
              {item.track_id != null ? `Track #${item.track_id}` : "—"}
              {item.frame_index != null ? ` · frame ${item.frame_index}` : ""}
            </div>
          </div>
        </button>
      ))}
    </div>
  );
}
