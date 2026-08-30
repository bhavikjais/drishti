import { Eye, ListChecks, X } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { cancelJob, listJobs } from "../api/jobs";
import { PageBody, PageHeader } from "../components/layout/AppLayout";
import { Panel } from "../components/common/Panel";
import { EmptyState, ErrorState, LoadingBlock } from "../components/common/States";
import { JobStatusBadge } from "../components/common/StatusBadge";
import { useApi } from "../hooks/useApi";
import { formatDuration } from "../lib/format";

export function Jobs() {
  const { status, data, error, refetch } = useApi(listJobs);
  const navigate = useNavigate();
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  async function handleCancel(jobId: string) {
    setCancellingId(jobId);
    try {
      await cancelJob(jobId);
      refetch();
    } finally {
      setCancellingId(null);
    }
  }

  return (
    <>
      <PageHeader title="Jobs" subtitle="Analysis job history" actions={<button onClick={() => navigate("/analysis")} className="rounded bg-accent-blue px-4 py-2 text-[12.5px] font-bold text-[#051020] hover:bg-[#59aeff]">NEW ANALYSIS</button>} />
      <PageBody>
        <Panel>
          {status === "loading" && <LoadingBlock label="Loading jobs…" />}
          {status === "error" && <ErrorState message={error} onRetry={refetch} />}
          {status === "success" && data.length === 0 && (
            <EmptyState icon={ListChecks} title="No jobs yet" description="Start an analysis to see it appear here." />
          )}
          {status === "success" && data.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-[12.5px]">
                <thead>
                  <tr>
                    <Th>Job</Th>
                    <Th>Modules</Th>
                    <Th>Status</Th>
                    <Th>Progress</Th>
                    <Th>Duration</Th>
                    <Th>Actions</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.map((job) => (
                    <tr key={job.job_id} className="border-b border-border-1 last:border-0">
                      <td className="px-3 py-3 font-mono text-text-primary">{job.job_id.slice(0, 8)}</td>
                      <td className="px-3 py-3 text-text-secondary">{job.summary?.modules_run?.join(", ") || job.kind}</td>
                      <td className="px-3 py-3"><JobStatusBadge status={job.status} /></td>
                      <td className="px-3 py-3 font-mono text-text-secondary">{Math.round(job.progress * 100)}%</td>
                      <td className="px-3 py-3 font-mono text-text-secondary">{formatDuration(job.elapsed_sec)}</td>
                      <td className="px-3 py-3">
                        <div className="flex items-center gap-2">
                          {job.status === "done" && (
                            <button onClick={() => navigate(`/results/${job.job_id}`)} className="inline-flex items-center gap-1 rounded border border-border-2 bg-bg-3 px-2.5 py-1.5 text-[11px] font-semibold text-text-secondary hover:bg-bg-4">
                              <Eye size={12} /> View
                            </button>
                          )}
                          {(job.status === "pending" || job.status === "running") && (
                            <>
                              <button onClick={() => navigate(`/processing/${job.job_id}`)} className="inline-flex items-center gap-1 rounded border border-border-2 bg-bg-3 px-2.5 py-1.5 text-[11px] font-semibold text-text-secondary hover:bg-bg-4">
                                <Eye size={12} /> View
                              </button>
                              <button
                                onClick={() => handleCancel(job.job_id)}
                                disabled={cancellingId === job.job_id}
                                className="inline-flex items-center gap-1 rounded border border-accent-red/35 px-2.5 py-1.5 text-[11px] font-semibold text-accent-red hover:bg-accent-red/10 disabled:opacity-50"
                              >
                                <X size={12} /> Cancel
                              </button>
                            </>
                          )}
                          {(job.status === "failed" || job.status === "cancelled") && <span className="text-text-tertiary">—</span>}
                        </div>
                      </td>
                    </tr>
                  ))}
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
