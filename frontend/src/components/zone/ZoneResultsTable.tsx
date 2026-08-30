import { formatTimestamp } from "../../lib/format";
import type { ZoneIntrusion } from "../../lib/deriveZoneIntrusions";

export function ZoneResultsTable({ intrusions }: { intrusions: ZoneIntrusion[] }) {
  if (intrusions.length === 0) {
    return <div className="py-6 text-center text-[12.5px] text-text-tertiary">No zone intrusions detected</div>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[12.5px]">
        <thead>
          <tr>
            <Th>Zone</Th>
            <Th>Track</Th>
            <Th>Entry</Th>
            <Th>Exit</Th>
            <Th>Dwell</Th>
          </tr>
        </thead>
        <tbody>
          {intrusions.map((row, i) => (
            <tr key={i} className="border-b border-border-1 last:border-0">
              <td className="px-3 py-2.5 font-semibold text-text-primary">{row.zoneLabel}</td>
              <td className="px-3 py-2.5 text-text-secondary">Track #{row.trackId}</td>
              <td className="px-3 py-2.5 font-mono text-accent-amber">{formatTimestamp(row.entrySec)}</td>
              <td className="px-3 py-2.5 font-mono text-accent-green">{row.exitSec != null ? formatTimestamp(row.exitSec) : "—"}</td>
              <td className="px-3 py-2.5 font-mono text-text-secondary">{row.dwellSec != null ? `${row.dwellSec.toFixed(1)}s` : "—"}</td>
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
