import { Clock, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { cancelJob } from "../api/jobs";
import { PageBody, PageHeader } from "../components/layout/AppLayout";
import { Panel } from "../components/common/Panel";
import { ProgressPanel } from "../components/jobs/ProgressPanel";
import { useJobPolling } from "../hooks/useJobPolling";

// Note: the backend only assembles a job's event list once the pipeline run
// completes (GET /api/jobs/{id}/events returns 409 until status=="done") -
// there is no partial/incremental event feed to poll during processing. So
// rather than fake a "live events" stream, this page is honest about that
// and shows real processing telemetry only; the full event timeline appears
// on the Results page the moment the job finishes (this page auto-navigates
// there as soon as status flips to "done").
export function Processing() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const { job, error, isTerminal } = useJobPolling(jobId);
  const [cancelling, setCancelling] = useState(false);

  useEffect(() => {
    if (job?.status === "done" && jobId) {
      navigate(`/results/${jobId}`, { replace: true });
    }
  }, [job?.status, jobId, navigate]);

  async function handleCancel() {
    if (!jobId) return;
    setCancelling(true);
    try {
      await cancelJob(jobId);
    } catch {
      // surfaced via next poll tick if it actually failed
    } finally {
      setCancelling(false);
    }
  }

  return (
    <>
      <PageHeader title="Analysis in Progress" subtitle={jobId ? `Job ${jobId.slice(0, 8)}` : undefined} />
      <PageBody narrow>
        {error && !job && (
          <div className="mb-4 rounded-md border border-accent-red/35 bg-accent-red/10 px-4 py-3 text-[12.5px] text-accent-red">{error}</div>
        )}
        {!job ? (
          <div className="flex items-center justify-center gap-3 py-24 text-text-tertiary">
            <Loader2 size={20} className="animate-spin" /> Connecting to analysis job…
          </div>
        ) : (
          <Panel title="Processing Status">
            <ProgressPanel job={job} onCancel={!isTerminal ? handleCancel : undefined} cancelling={cancelling} />

            {(job.status === "running" || job.status === "pending") && (
              <div className="mt-5 flex items-center gap-2 rounded-md border border-border-1 bg-bg-3 px-3.5 py-3 text-[12px] text-text-tertiary">
                <Clock size={14} className="shrink-0" />
                Events and evidence will appear on the results page once this analysis completes.
              </div>
            )}
            {job.status === "cancelled" && (
              <button onClick={() => navigate("/analysis")} className="mt-5 w-full rounded bg-bg-3 py-2.5 text-[12.5px] font-semibold text-text-secondary hover:bg-bg-4">
                Start New Analysis
              </button>
            )}
            {job.status === "failed" && (
              <button onClick={() => navigate("/analysis")} className="mt-5 w-full rounded bg-bg-3 py-2.5 text-[12.5px] font-semibold text-text-secondary hover:bg-bg-4">
                Back to Analysis
              </button>
            )}
          </Panel>
        )}
      </PageBody>
    </>
  );
}
