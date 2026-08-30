import { Activity, Car, Radar, ScanFace, ShieldCheck, Video } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { cancelJob } from "../api/jobs";
import { PageBody, PageHeader } from "../components/layout/AppLayout";
import { MetricCard } from "../components/common/MetricCard";
import { Panel } from "../components/common/Panel";
import { EmptyState, ErrorState, SkeletonCard } from "../components/common/States";
import { EventTimeline } from "../components/events/EventTimeline";
import { JobStatusBadge } from "../components/common/StatusBadge";
import { ProgressPanel } from "../components/jobs/ProgressPanel";
import { useDashboardData } from "../hooks/useDashboardData";
import { useState } from "react";

export function Dashboard() {
  const { loading, error, jobs, metrics, activeJob, recentEvents, refetch } = useDashboardData();
  const navigate = useNavigate();
  const [cancelling, setCancelling] = useState(false);

  async function handleCancelActive() {
    if (!activeJob) return;
    setCancelling(true);
    try {
      await cancelJob(activeJob.job_id);
      refetch();
    } finally {
      setCancelling(false);
    }
  }

  return (
    <>
      <PageHeader
        title="BorderWatch"
        subtitle="AI Video Intelligence Command Center"
        actions={
          <button
            onClick={() => navigate("/analysis")}
            className="rounded bg-accent-blue px-4 py-2 text-[12.5px] font-bold text-[#051020] hover:bg-[#59aeff]"
          >
            START NEW ANALYSIS
          </button>
        }
      />
      <PageBody>
        {error && <ErrorState message={error} onRetry={refetch} />}

        {!error && loading && (
          <div className="grid grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-4">
            {Array.from({ length: 5 }).map((_, i) => <SkeletonCard key={i} />)}
          </div>
        )}

        {!error && !loading && jobs.length === 0 && (
          <Panel>
            <EmptyState
              icon={Video}
              title="No analyses yet"
              description="Upload surveillance footage to begin an analysis. BorderWatch will detect targets, plates, zone intrusions and behavioral alerts."
              action={
                <button onClick={() => navigate("/analysis")} className="rounded bg-accent-blue px-5 py-2.5 text-[12.5px] font-bold text-[#051020] hover:bg-[#59aeff]">
                  START NEW ANALYSIS
                </button>
              }
            />
          </Panel>
        )}

        {!error && !loading && jobs.length > 0 && (
          <>
            <div className="mb-5 grid grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-4">
              <MetricCard label="Videos Analyzed" value={metrics.videosAnalyzed} icon={Video} />
              <MetricCard label="Targets Identified" value={metrics.targetsIdentified} icon={ScanFace} accent={metrics.targetsIdentified ? "red" : "default"} />
              <MetricCard label="Vehicles Detected" value={metrics.vehiclesDetected} icon={Car} accent="blue" />
              <MetricCard label="Plates Read" value={metrics.platesRead} icon={Radar} />
              <MetricCard label="Security Events" value={metrics.securityEvents} icon={Activity} accent={metrics.securityEvents ? "amber" : "default"} />
            </div>

            <div className="grid grid-cols-[1fr_380px] gap-5 max-[1200px]:grid-cols-1">
              <div className="flex flex-col gap-5">
                <Panel title={activeJob ? "Active Analysis" : "System"} meta={activeJob ? undefined : "No job currently processing"}>
                  {activeJob ? (
                    <ProgressPanel
                      job={activeJob}
                      onCancel={handleCancelActive}
                      cancelling={cancelling}
                      onView={() => navigate(`/results/${activeJob.job_id}`)}
                    />
                  ) : (
                    <div className="flex items-center gap-3 text-[12.5px] text-text-tertiary">
                      <ShieldCheck size={18} className="text-accent-green" />
                      All clear — no analysis currently running.
                    </div>
                  )}
                </Panel>

                <Panel title="Recent Analyses">
                  <div className="flex flex-col divide-y divide-border-1">
                    {jobs.slice(0, 6).map((job) => (
                      <button
                        key={job.job_id}
                        onClick={() => navigate(job.status === "done" ? `/results/${job.job_id}` : `/processing/${job.job_id}`)}
                        className="flex items-center justify-between py-3 text-left transition-colors first:pt-0 last:pb-0 hover:bg-bg-3"
                      >
                        <div>
                          <div className="text-[12.5px] font-semibold text-text-primary">Job {job.job_id.slice(0, 8)}</div>
                          <div className="mt-0.5 text-[11px] text-text-tertiary">
                            {job.summary?.modules_run?.join(" · ") || job.kind}
                          </div>
                        </div>
                        <JobStatusBadge status={job.status} />
                      </button>
                    ))}
                  </div>
                </Panel>
              </div>

              <Panel title="Recent Security Events" meta={recentEvents.length ? String(recentEvents.length) : undefined}>
                {recentEvents.length === 0 ? (
                  <div className="py-8 text-center text-[12.5px] text-text-tertiary">No security events detected</div>
                ) : (
                  <div className="max-h-[560px] overflow-y-auto">
                    <EventTimeline
                      events={recentEvents.map((r) => r.event)}
                      onSelect={(ev) => {
                        const match = recentEvents.find((r) => r.event === ev);
                        if (match) navigate(`/results/${match.job.job_id}`);
                      }}
                    />
                  </div>
                )}
              </Panel>
            </div>
          </>
        )}
      </PageBody>
    </>
  );
}
