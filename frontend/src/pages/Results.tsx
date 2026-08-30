import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { getJobEvidence, getJobEvents, jobOutputUrl } from "../api/jobs";
import type { BwEvent, EvidenceItem } from "../api/types";
import { titleCase } from "../lib/format";
import { PageBody, PageHeader } from "../components/layout/AppLayout";
import { Panel, SectionTitle } from "../components/common/Panel";
import { MetricCard } from "../components/common/MetricCard";
import { StatusBadge } from "../components/common/StatusBadge";
import { EmptyState, ErrorState, LoadingBlock } from "../components/common/States";
import { VideoPlayer, type VideoPlayerHandle } from "../components/video/VideoPlayer";
import { EventTimeline } from "../components/events/EventTimeline";
import { EvidenceGrid } from "../components/evidence/EvidenceGrid";
import { Modal } from "../components/common/Modal";
import { jobEvidenceFileUrl } from "../api/jobs";
import { TargetCard } from "../components/target/TargetCard";
import { PlateResultCard } from "../components/anpr/PlateResultCard";
import { PlatesTable } from "../components/anpr/PlatesTable";
import { ZoneResultsTable } from "../components/zone/ZoneResultsTable";
import { BehaviorResultsList } from "../components/behavior/BehaviorResultsList";
import { LowlightSummaryCard } from "../components/common/LowlightSummaryCard";
import { deriveZoneIntrusions } from "../lib/deriveZoneIntrusions";
import { useJobPolling } from "../hooks/useJobPolling";
import { Radar } from "lucide-react";

export function Results() {
  const { jobId } = useParams<{ jobId: string }>();
  const { job, error: jobError } = useJobPolling(jobId);
  const [events, setEvents] = useState<BwEvent[] | null>(null);
  const [evidence, setEvidence] = useState<EvidenceItem[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<BwEvent | null>(null);
  const [evidenceModal, setEvidenceModal] = useState<EvidenceItem | null>(null);
  const playerRef = useRef<VideoPlayerHandle>(null);

  useEffect(() => {
    if (job?.status !== "done" || !jobId) return;
    Promise.all([getJobEvents(jobId), getJobEvidence(jobId)])
      .then(([ev, ec]) => {
        setEvents(ev);
        setEvidence(ec);
      })
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Failed to load analysis results"));
  }, [job?.status, jobId]);

  const summary = job?.summary;
  const plateCount = summary?.anpr?.detected_plates?.length ?? 0;
  const zoneIntrusions = useMemo(() => deriveZoneIntrusions(events ?? [], summary?.zones ?? []), [events, summary?.zones]);

  function jumpToEvent(ev: BwEvent) {
    setSelectedEvent(ev);
    playerRef.current?.seekTo(ev.timestamp_sec);
  }

  if (!jobId) return null;

  if (jobError && !job) return <PageShell><ErrorState message={jobError} /></PageShell>;
  if (!job) return <PageShell><LoadingBlock label="Loading analysis…" /></PageShell>;
  if (job.status !== "done") {
    return (
      <PageShell>
        <EmptyState icon={Radar} title={`Analysis ${job.status}`} description="This job hasn't completed yet. Return to the processing view to watch its progress." />
      </PageShell>
    );
  }
  if (loadError) return <PageShell><ErrorState message={loadError} /></PageShell>;
  if (!events || !evidence) return <PageShell><LoadingBlock label="Loading events and evidence…" /></PageShell>;

  const title = summary?.person_id ? "Target Person Identification" : "BorderWatch Analysis Results";

  return (
    <>
      <PageHeader
        title={title}
        subtitle={`Job ${jobId.slice(0, 8)}`}
        actions={<StatusBadge label="COMPLETED" severity="green" />}
      />
      <PageBody>
        <div className="mb-5 grid grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-4">
          <MetricCard label="Target Track" value={summary?.person_id?.confirmed ? `#${summary.person_id.target_track_id}` : "—"} accent={summary?.person_id?.confirmed ? "red" : "default"} />
          <MetricCard label="Video Duration" value={summary?.video_info ? `${summary.video_info.duration_sec.toFixed(1)}s` : "—"} />
          <MetricCard label="Frames Processed" value={job.frames_processed ?? "—"} />
          <MetricCard label="Events" value={events.length} accent="blue" />
          <MetricCard label="Plates Read" value={summary?.anpr ? plateCount : "—"} />
          <MetricCard label="Zone Intrusions" value={summary?.zones ? zoneIntrusions.length : "—"} accent={zoneIntrusions.length ? "amber" : "default"} />
        </div>

        <div className="grid grid-cols-[1fr_360px] gap-5 max-[1200px]:grid-cols-1">
          <div className="flex flex-col gap-5">
            <VideoPlayer ref={playerRef} src={jobOutputUrl(jobId)} />

            {summary?.person_id && (
              <Panel title="Target Visualization">
                <TargetCard summary={summary.person_id} events={events} />
                <p className="mt-3 text-[11px] text-text-tertiary">
                  The red target overlay is already rendered into the output video by the backend — this panel shows supporting detail only.
                </p>
              </Panel>
            )}

            {summary?.anpr && (
              <Panel title="ANPR Results" meta={`${plateCount} plate${plateCount === 1 ? "" : "s"} detected`}>
                {summary.anpr.searched_plate && (
                  <div className="mb-5">
                    <SectionTitle>Plate Search Result</SectionTitle>
                    <PlateResultCard
                      target={summary.anpr.target!}
                      searchedPlate={summary.anpr.searched_plate}
                      onJumpToVideo={summary.anpr.target?.first_seen_sec != null ? () => playerRef.current?.seekTo(summary.anpr!.target!.first_seen_sec!) : undefined}
                    />
                  </div>
                )}
                <SectionTitle>Plates Detected</SectionTitle>
                <PlatesTable plates={summary.anpr.detected_plates} />
              </Panel>
            )}

            {summary?.zones && (
              <Panel title="Zone Intrusions">
                <ZoneResultsTable intrusions={zoneIntrusions} />
              </Panel>
            )}

            {summary?.behavior && (
              <Panel title="Behavioral Analytics">
                <BehaviorResultsList events={events} />
              </Panel>
            )}

            {summary?.lowlight && (
              <Panel title="Low-Light Enhancement">
                <LowlightSummaryCard summary={summary.lowlight} />
              </Panel>
            )}

            <Panel title="Evidence" meta={`${evidence.length} item${evidence.length === 1 ? "" : "s"}`}>
              <EvidenceGrid jobId={jobId} items={evidence} onOpen={setEvidenceModal} />
            </Panel>
          </div>

          <div className="flex flex-col gap-5">
            <Panel title="Event Timeline" meta={`${events.length}`}>
              <div className="max-h-[640px] overflow-y-auto">
                <EventTimeline events={events} selectedId={selectedEvent?.event_id} onSelect={jumpToEvent} />
              </div>
            </Panel>
          </div>
        </div>
      </PageBody>

      {evidenceModal && (
        <Modal title={evidenceModal.event_type ? titleCase(evidenceModal.event_type) : "Evidence"} onClose={() => setEvidenceModal(null)}>
          <img src={jobEvidenceFileUrl(jobId, evidenceModal.filename)} alt="Evidence" className="w-full rounded-md border border-border-1" />
          <div className="mt-3 flex justify-between text-[12px] text-text-tertiary">
            <span>{evidenceModal.track_id != null ? `Track #${evidenceModal.track_id}` : "—"}</span>
            <span>Frame {evidenceModal.frame_index ?? "—"}</span>
          </div>
        </Modal>
      )}
    </>
  );
}

function PageShell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <PageHeader title="Analysis Results" />
      <PageBody>
        <Panel>{children}</Panel>
      </PageBody>
    </>
  );
}
