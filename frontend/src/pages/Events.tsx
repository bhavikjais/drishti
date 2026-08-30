import { Activity, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getJobEvents, listJobs } from "../api/jobs";
import type { BwEvent, JobStatusOut } from "../api/types";
import { PageBody, PageHeader } from "../components/layout/AppLayout";
import { Panel } from "../components/common/Panel";
import { EmptyState, ErrorState, LoadingBlock } from "../components/common/States";
import { eventMeta } from "../lib/eventMeta";
import { formatTimestamp, titleCase } from "../lib/format";
import { useApi } from "../hooks/useApi";

const MAX_JOBS_SCANNED = 25;

interface Row {
  job: JobStatusOut;
  event: BwEvent;
}

async function loadAllEvents(): Promise<Row[]> {
  const jobs = await listJobs();
  const done = jobs.filter((j) => j.status === "done").slice(0, MAX_JOBS_SCANNED);
  const lists = await Promise.all(
    done.map(async (job) => {
      try {
        const events = await getJobEvents(job.job_id);
        return events.map((event) => ({ job, event }));
      } catch {
        return [];
      }
    }),
  );
  return lists.flat().sort((a, b) => b.event.timestamp_sec - a.event.timestamp_sec);
}

export function Events() {
  const { status, data, error, refetch } = useApi(loadAllEvents);
  const navigate = useNavigate();
  const [typeFilter, setTypeFilter] = useState("");
  const [trackFilter, setTrackFilter] = useState("");
  const [search, setSearch] = useState("");

  const eventTypes = useMemo(() => Array.from(new Set((data ?? []).map((r) => r.event.type))).sort(), [data]);

  const filtered = useMemo(() => {
    if (!data) return [];
    return data.filter(({ event }) => {
      if (typeFilter && event.type !== typeFilter) return false;
      if (trackFilter && String(event.track_id) !== trackFilter) return false;
      if (search) {
        const haystack = `${event.type} ${event.track_id ?? ""} ${event.zone ?? ""} ${event.plate ?? event.data?.text ?? ""}`.toLowerCase();
        if (!haystack.includes(search.toLowerCase())) return false;
      }
      return true;
    });
  }, [data, typeFilter, trackFilter, search]);

  return (
    <>
      <PageHeader title="Events" subtitle="Full security event investigation" />
      <PageBody>
        <Panel className="mb-4" tight>
          <div className="flex flex-wrap items-center gap-3 p-2">
            <div className="relative flex-1 min-w-[200px]">
              <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary" />
              <input
                className="w-full rounded border border-border-2 bg-bg-3 py-2 pl-9 pr-3 text-[12.5px] text-text-primary placeholder:text-text-disabled focus:border-accent-blue focus:outline-none"
                placeholder="Search track, zone, plate…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="rounded border border-border-2 bg-bg-3 px-3 py-2 text-[12px] text-text-primary focus:border-accent-blue focus:outline-none">
              <option value="">All Event Types</option>
              {eventTypes.map((t) => (
                <option key={t} value={t}>{titleCase(t)}</option>
              ))}
            </select>
            <input
              className="w-28 rounded border border-border-2 bg-bg-3 px-3 py-2 text-[12px] text-text-primary placeholder:text-text-disabled focus:border-accent-blue focus:outline-none"
              placeholder="Track ID"
              value={trackFilter}
              onChange={(e) => setTrackFilter(e.target.value.replace(/\D/g, ""))}
            />
          </div>
        </Panel>

        <Panel>
          {status === "loading" && <LoadingBlock label="Loading events…" />}
          {status === "error" && <ErrorState message={error} onRetry={refetch} />}
          {status === "success" && filtered.length === 0 && (
            <EmptyState icon={Activity} title="No security events detected" description={data && data.length > 0 ? "No events match the current filters." : "Run an analysis to start generating events."} />
          )}
          {status === "success" && filtered.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-[12.5px]">
                <thead>
                  <tr>
                    <Th>Timestamp</Th>
                    <Th>Type</Th>
                    <Th>Track</Th>
                    <Th>Confidence</Th>
                    <Th>Source Video</Th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((row, i) => {
                    const meta = eventMeta(row.event.type);
                    const Icon = meta.icon;
                    const conf = row.event.confidence ?? row.event.data?.confidence ?? row.event.data?.similarity;
                    return (
                      <tr key={`${row.job.job_id}-${row.event.event_id ?? i}`} className="cursor-pointer border-b border-border-1 transition-colors last:border-0 hover:bg-bg-3" onClick={() => navigate(`/results/${row.job.job_id}`)}>
                        <td className="px-3 py-2.5 font-mono text-text-secondary">{formatTimestamp(row.event.timestamp_sec)}</td>
                        <td className="px-3 py-2.5">
                          <span className="inline-flex items-center gap-1.5 font-semibold text-text-primary"><Icon size={13} /> {meta.label}</span>
                        </td>
                        <td className="px-3 py-2.5 text-text-secondary">{row.event.track_id != null ? `#${row.event.track_id}` : "—"}</td>
                        <td className="px-3 py-2.5 font-mono text-text-secondary">{typeof conf === "number" ? `${(conf > 1 ? conf : conf * 100).toFixed(1)}%` : "—"}</td>
                        <td className="px-3 py-2.5 font-mono text-text-tertiary">{row.job.job_id.slice(0, 8)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </PageBody>
    </>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return <th className="border-b border-border-1 px-3 py-2 text-left text-[10.5px] font-semibold tracking-wide text-text-tertiary">{children}</th>;
}
