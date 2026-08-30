import { CarFront, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { searchPlate } from "../api/jobs";
import type { JobStatusOut } from "../api/types";
import { PageBody, PageHeader } from "../components/layout/AppLayout";
import { Panel } from "../components/common/Panel";
import { UploadZone } from "../components/analysis/UploadZone";
import { PlateResultCard } from "../components/anpr/PlateResultCard";
import { useApi } from "../hooks/useApi";
import { normalizePlateForDisplay } from "../lib/format";
import { listJobs } from "../api/jobs";
import { useJobPolling } from "../hooks/useJobPolling";

async function loadRecentSearches(): Promise<JobStatusOut[]> {
  const jobs = await listJobs();
  return jobs.filter((j) => j.summary?.anpr?.searched_plate).slice(0, 8);
}

export function AnprSearch() {
  const [videoId, setVideoId] = useState<string | null>(null);
  const [plate, setPlate] = useState("");
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { job } = useJobPolling(activeJobId ?? undefined);
  const { data: recent, refetch: refetchRecent } = useApi(loadRecentSearches);
  const navigate = useNavigate();

  async function handleSearch() {
    if (!videoId || !plate.trim()) return;
    setStarting(true);
    setError(null);
    try {
      const result = await searchPlate({ video_id: videoId, plate: plate.trim() });
      setActiveJobId(result.job_id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to start plate search");
    } finally {
      setStarting(false);
    }
  }

  const searching = job != null && job.status !== "done" && job.status !== "failed" && job.status !== "cancelled";
  const target = job?.summary?.anpr?.target;

  // refresh "Recent Searches" once a new search job actually completes
  useEffect(() => {
    if (job?.status === "done") refetchRecent();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.status]);

  return (
    <>
      <PageHeader title="Vehicle Intelligence" subtitle="Search confirmed plate observations across analyzed footage" />
      <PageBody narrow>
        <Panel title="Search a Plate">
          {!videoId ? (
            <UploadZone
              onUploaded={(v) => {
                setVideoId(v.video_id);
              }}
            />
          ) : (
            <>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <CarFront size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary" />
                  <input
                    className="w-full rounded border border-border-2 bg-bg-3 py-3 pl-10 pr-3 font-mono text-[15px] uppercase tracking-widest text-text-primary placeholder:text-text-disabled placeholder:tracking-normal placeholder:normal-case focus:border-accent-blue focus:outline-none"
                    placeholder="Enter plate number…"
                    value={plate}
                    onChange={(e) => setPlate(normalizePlateForDisplay(e.target.value))}
                    onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                  />
                </div>
                <button
                  onClick={handleSearch}
                  disabled={!plate.trim() || starting || searching}
                  className="inline-flex items-center gap-2 rounded bg-accent-blue px-6 py-3 text-[13px] font-bold text-[#051020] hover:bg-[#59aeff] disabled:opacity-40"
                >
                  <Search size={15} /> {starting || searching ? "SEARCHING…" : "SEARCH"}
                </button>
              </div>
              <button onClick={() => { setVideoId(null); setActiveJobId(null); }} className="mt-3 text-[11.5px] text-text-tertiary hover:text-text-secondary">
                Use a different video
              </button>
            </>
          )}
          {error && <div className="mt-3 rounded-md border border-accent-red/35 bg-accent-red/10 px-3 py-2.5 text-[12px] text-accent-red">{error}</div>}
        </Panel>

        {job && job.status === "done" && target && (
          <div className="mt-5">
            <PlateResultCard
              target={target}
              searchedPlate={job.summary?.anpr?.searched_plate ?? plate}
              onJumpToVideo={() => activeJobId && navigate(`/results/${activeJobId}`)}
              onViewEvidence={() => activeJobId && navigate(`/results/${activeJobId}`)}
            />
          </div>
        )}
        {job && job.status === "failed" && (
          <div className="mt-5 rounded-md border border-accent-red/35 bg-accent-red/10 px-4 py-3 text-[12.5px] text-accent-red">{job.error}</div>
        )}

        {recent && recent.length > 0 && (
          <Panel title="Recent Searches" className="mt-5">
            <div className="flex flex-col divide-y divide-border-1">
              {recent.map((j) => (
                <button
                  key={j.job_id}
                  onClick={() => navigate(`/results/${j.job_id}`)}
                  className="flex items-center justify-between py-3 text-left first:pt-0 last:pb-0 hover:bg-bg-3"
                >
                  <span className="font-mono text-[13px] tracking-wide text-text-primary">{j.summary?.anpr?.searched_plate}</span>
                  <span className={`text-[11.5px] font-semibold ${j.summary?.anpr?.target?.found ? "text-accent-green" : "text-text-tertiary"}`}>
                    {j.summary?.anpr?.target?.found ? "FOUND" : "NOT FOUND"}
                  </span>
                </button>
              ))}
            </div>
          </Panel>
        )}
      </PageBody>
    </>
  );
}
