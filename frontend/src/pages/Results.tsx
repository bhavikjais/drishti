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
import { NotificationsPanel } from "../components/notifications/NotificationsPanel";
import { EvidenceGrid } from "../components/evidence/EvidenceGrid";
import { Modal } from "../components/common/Modal";
import { jobEvidenceFileUrl } from "../api/jobs";
import { TargetCard } from "../components/target/TargetCard";
import { PlateResultCard } from "../components/anpr/PlateResultCard";
import { PlatesTable } from "../components/anpr/PlatesTable";
import { ZoneResultsTable } from "../components/zone/ZoneResultsTable";
import { BehaviorResultsList } from "../components/behavior/BehaviorResultsList";
import { LowlightSummaryCard } from "../components/common/LowlightSummaryCard";
import { DehazeSummaryCard } from "../components/common/DehazeSummaryCard";
import { deriveZoneIntrusions } from "../lib/deriveZoneIntrusions";
import { useJobPolling } from "../hooks/useJobPolling";
import { playSiren } from "../lib/siren";
import { eventMeta, isNotifiable } from "../lib/eventMeta";
import { Radar } from "lucide-react";

// PREDICTED_ZONE_CROSSING (plain zone module - no target locked) and
// TARGET_ZONE_INTRUSION_PREDICTED (zone/forecast.py's intent-forecasting
// correlated against a locked target) both mean "this track's trajectory is
// projected to cross into a restricted zone soon". Sounding the alarm on
// those, not just on TARGET_CONFIRMED/REACQUIRED, is what makes this a
// predictive warning instead of a reactive one.
const ALARM_EVENT_TYPES = new Set([
  "TARGET_CONFIRMED", "TARGET_REACQUIRED", "TARGET_ZONE_INTRUSION_PREDICTED", "PREDICTED_ZONE_CROSSING",
]);

export function Results() {
  const { jobId } = useParams<{ jobId: string }>();
  const { job, error: jobError } = useJobPolling(jobId);
  const [events, setEvents] = useState<BwEvent[] | null>(null);
  const [evidence, setEvidence] = useState<EvidenceItem[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<BwEvent | null>(null);
  const [evidenceModal, setEvidenceModal] = useState<EvidenceItem | null>(null);
  const playerRef = useRef<VideoPlayerHandle>(null);
  const firedAlertsRef = useRef<Set<number>>(new Set());
  const lastVideoTimeRef = useRef(0);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [activeAlert, setActiveAlert] = useState<BwEvent | null>(null);

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
  const predictedCrossingCount = useMemo(
    () => (events ?? []).filter((ev) => ev.type === "PREDICTED_ZONE_CROSSING").length,
    [events],
  );
  const alarmEvents = useMemo(() => (events ?? []).filter((ev) => ALARM_EVENT_TYPES.has(ev.type)), [events]);

  function fireAlarm(ev: BwEvent | null) {
    playSiren();
    if (!ev) return;
    setActiveAlert(ev);
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    toastTimerRef.current = setTimeout(() => setActiveAlert(null), 5000);
  }

  // Sound the alarm once as soon as we learn the target was confirmed in
  // this footage, then again every time video playback crosses a
  // TARGET_CONFIRMED/TARGET_REACQUIRED/predicted-crossing moment (forward
  // playback or seek).
  useEffect(() => {
    if (summary?.person_id?.confirmed) playSiren();
  }, [summary?.person_id?.confirmed]);

  function handleVideoTimeUpdate(t: number) {
    const last = lastVideoTimeRef.current;
    if (t < last - 0.5) {
      for (const ts of firedAlertsRef.current) {
        if (ts > t) firedAlertsRef.current.delete(ts);
      }
    }
    for (const ev of alarmEvents) {
      const ts = ev.timestamp_sec;
      if (ts <= t && ts > last - 0.05 && !firedAlertsRef.current.has(ts)) {
        firedAlertsRef.current.add(ts);
        fireAlarm(ev);
      }
    }
    lastVideoTimeRef.current = t;
  }

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

  const title = summary?.person_id ? "Target Person Identification" : "Drishti Analysis Results";

  return (
    <>
      {activeAlert && <AlarmToast event={activeAlert} onDismiss={() => setActiveAlert(null)} />}

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
          <MetricCard label="Crossings Predicted" value={summary?.zones ? predictedCrossingCount : "—"} accent={predictedCrossingCount ? "amber" : "default"} />
        </div>

        <div className="grid grid-cols-[1fr_360px] gap-5 max-[1200px]:grid-cols-1">
          <div className="flex flex-col gap-5">
            <VideoPlayer ref={playerRef} src={jobOutputUrl(jobId)} onTimeUpdate={handleVideoTimeUpdate} />

            <Panel title="Notifications" meta={`${events.filter((ev) => isNotifiable(ev.type)).length} alert-worthy`}>
              <NotificationsPanel jobId={jobId} events={events} evidence={evidence} selectedId={selectedEvent?.event_id} onSelect={jumpToEvent} />
            </Panel>

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

            {summary?.dehaze && (
              <Panel title="Haze / Fog Removal">
                <DehazeSummaryCard summary={summary.dehaze} />
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

const TOAST_SEVERITY_CLASS: Record<string, string> = {
  red: "border-accent-red/40 bg-accent-red/10 text-accent-red",
  amber: "border-accent-amber/40 bg-accent-amber/10 text-accent-amber",
  green: "border-accent-green/40 bg-accent-green/10 text-accent-green",
  blue: "border-accent-blue/40 bg-accent-blue/10 text-accent-blue",
  neutral: "border-border-2 bg-bg-3 text-text-secondary",
};

// On-screen alarm popup, separate from the siren sound and from the banner
// already burned into the output video - so the alert is noticeable even if
// the operator isn't staring at the video frame itself when it fires.
function AlarmToast({ event, onDismiss }: { event: BwEvent; onDismiss: () => void }) {
  const meta = eventMeta(event.type);
  const Icon = meta.icon;
  const eta = typeof event.data?.eta_sec === "number" ? event.data.eta_sec : null;

  return (
    <div className="fixed right-5 top-5 z-50 w-[320px] animate-[pulse_1.5s_ease-in-out_1]">
      <div className={`flex items-start gap-3 rounded-lg border px-4 py-3 shadow-lg backdrop-blur ${TOAST_SEVERITY_CLASS[meta.severity]}`}>
        <Icon size={18} className="mt-0.5 shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="text-[12.5px] font-semibold">{meta.label}</div>
          <div className="mt-0.5 text-[11.5px] opacity-80">
            {event.track_id != null && `Track #${event.track_id}`}
            {eta != null && ` · ETA ${eta.toFixed(1)}s to restricted area`}
            {event.zone && ` · ${event.zone}`}
          </div>
        </div>
        <button onClick={onDismiss} className="shrink-0 text-[11px] opacity-60 hover:opacity-100" aria-label="Dismiss">
          ✕
        </button>
      </div>
    </div>
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
