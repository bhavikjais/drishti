import { formatConfidence } from "../../lib/format";
import type { DetectedPlate } from "../../api/types";

export function PlatesTable({ plates }: { plates: DetectedPlate[] }) {
  if (plates.length === 0) {
    return <div className="py-6 text-center text-[12.5px] text-text-tertiary">No plates detected in this video</div>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[12.5px]">
        <thead>
          <tr>
            <Th>Plate</Th>
            <Th>Confidence</Th>
            <Th>Track</Th>
            <Th>Observations</Th>
            <Th>Status</Th>
          </tr>
        </thead>
        <tbody>
          {plates.map((p) => (
            <tr key={p.track_id} className="border-b border-border-1 last:border-0">
              <Td className="font-mono font-bold tracking-wider text-text-primary">{p.text}</Td>
              <Td>{formatConfidence(p.mean_confidence)}</Td>
              <Td>Track #{p.track_id}</Td>
              <Td>{p.observation_count}</Td>
              <Td>
                {p.confirmed ? (
                  <span className="rounded-full border border-accent-green/35 bg-accent-green/12 px-2 py-0.5 text-[10.5px] font-semibold text-accent-green">CONFIRMED</span>
                ) : (
                  <span className="rounded-full border border-border-2 bg-bg-3 px-2 py-0.5 text-[10.5px] font-semibold text-text-tertiary">PROVISIONAL</span>
                )}
              </Td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return <th className="border-b border-border-1 px-3 py-2 text-left text-[10.5px] font-semibold tracking-wide text-text-tertiary">{children}</th>;
}
function Td({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <td className={`px-3 py-2.5 text-text-secondary ${className}`}>{children}</td>;
}
