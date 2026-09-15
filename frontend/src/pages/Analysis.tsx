import { AlertTriangle, Bell, CloudFog, Eye, Info, Moon, Search, ShieldAlert, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { startCombinedJob } from "../api/jobs";
import type { CombinedJobRequest, VideoUpload, Zone } from "../api/types";
import { BehaviorConfigPanel, DEFAULT_BEHAVIOR_CONFIG, type BehaviorConfigValues } from "../components/analysis/BehaviorConfigPanel";
import { ModuleCard } from "../components/analysis/ModuleCard";
import { ReferencePhotoUpload } from "../components/analysis/ReferencePhotoUpload";
import { StepIndicator } from "../components/analysis/StepIndicator";
import { UploadZone, VideoSummary } from "../components/analysis/UploadZone";
import { ZoneDrawer } from "../components/analysis/ZoneDrawer";
import { PageBody, PageHeader } from "../components/layout/AppLayout";
import { Panel, SectionTitle } from "../components/common/Panel";

interface ModuleFlags {
  person_id: boolean;
  anpr: boolean;
  zone: boolean;
  behavior: boolean;
  lowlight: boolean;
  dehaze: boolean;
}

const OPEN_PARAM_MAP: Record<string, keyof ModuleFlags | null> = {
  person_id: "person_id",
  anpr: "anpr",
  zone: "zone",
  behavior: "behavior",
  lowlight: "lowlight",
  dehaze: "dehaze",
  human_detection: null,
  vehicle_detection: null,
};

export function Analysis() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [step, setStep] = useState(1);
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [video, setVideo] = useState<VideoUpload | null>(null);
  const [modules, setModules] = useState<ModuleFlags>({ person_id: false, anpr: false, zone: false, behavior: false, lowlight: false, dehaze: false });
  const [deepLinkNote, setDeepLinkNote] = useState<string | null>(null);

  const [referenceSetId, setReferenceSetId] = useState<string | null>(null);
  const [referenceCount, setReferenceCount] = useState(0);
  const [targetPlate, setTargetPlate] = useState("");
  const [zones, setZones] = useState<Zone[]>([]);
  const [behaviorConfig, setBehaviorConfig] = useState<BehaviorConfigValues>(DEFAULT_BEHAVIOR_CONFIG);
  const [webhookUrl, setWebhookUrl] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const videoPreviewUrl = useMemo(() => (videoFile ? URL.createObjectURL(videoFile) : undefined), [videoFile]);
  useEffect(() => {
    return () => {
      if (videoPreviewUrl) URL.revokeObjectURL(videoPreviewUrl);
    };
  }, [videoPreviewUrl]);

  useEffect(() => {
    const open = searchParams.get("open");
    if (!open) return;
    const key = OPEN_PARAM_MAP[open];
    if (key) {
      setModules((m) => ({ ...m, [key]: true }));
    } else if (open === "human_detection" || open === "vehicle_detection") {
      setDeepLinkNote(
        `${open === "human_detection" ? "Human" : "Vehicle"} detection isn't a standalone module - it's the shared detector every module below already uses. Select Zone Intrusion or Behavioral Analytics to track people/vehicles directly, or Target Person ID / ANPR to identify specific ones.`,
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedCount = Object.values(modules).filter(Boolean).length;

  function toggleModule(key: keyof ModuleFlags) {
    setModules((m) => ({ ...m, [key]: !m[key] }));
  }

  const configValid = useMemo(() => {
    if (modules.person_id && !referenceSetId) return false;
    if (modules.zone && zones.length === 0) return false;
    return true;
  }, [modules, referenceSetId, zones]);

  const canGoStep2 = !!video;
  const canGoStep3 = canGoStep2 && selectedCount > 0;
  const canGoStep4 = canGoStep3 && configValid;

  async function handleStart() {
    if (!video || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const req: CombinedJobRequest = { video_id: video.video_id };
      if (modules.person_id && referenceSetId) req.person_id = { reference_set_id: referenceSetId };
      if (modules.anpr) req.anpr = { target_plate: targetPlate.trim() || null };
      if (modules.zone) req.zone_ids = zones.map((z) => z.zone_id);
      if (modules.behavior) {
        req.behavior = {
          config: {
            loitering_seconds: behaviorConfig.loitering_seconds,
            direction_change_degrees: behaviorConfig.direction_change_degrees,
            speed_threshold_px_per_sec: behaviorConfig.speed_threshold_px_per_sec,
            reversal_count: behaviorConfig.reversal_count,
            loitering_radius_px: behaviorConfig.loitering_radius_px,
            reversal_angle_degrees: behaviorConfig.reversal_angle_degrees,
            acceleration_threshold_px_per_sec: behaviorConfig.acceleration_threshold_px_per_sec,
            behavior_cooldown_seconds: behaviorConfig.behavior_cooldown_seconds,
          },
        };
      }
      if (modules.lowlight) req.lowlight = {};
      if (modules.dehaze) req.dehaze = {};
      if (webhookUrl.trim()) req.alert = { webhook_url: webhookUrl.trim() };

      const job = await startCombinedJob(req);
      navigate(`/processing/${job.job_id}`);
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : "Failed to start analysis");
      setSubmitting(false);
    }
  }

  return (
    <>
      <PageHeader title="New Analysis" subtitle="Configure and launch a Drishti video analysis" />
      <PageBody narrow>
        <StepIndicator current={step} />

        {step === 1 && (
          <Panel title="Step 1 · Upload Surveillance Video">
            {!video ? (
              <UploadZone
                onUploaded={(v, file) => {
                  setVideo(v);
                  setVideoFile(file);
                  setStep(2);
                }}
              />
            ) : (
              <div>
                <video src={videoPreviewUrl} controls className="mb-4 max-h-80 w-full rounded-lg border border-border-1 bg-black" />
                <VideoSummary filename={video.filename} video={video.video_info} />
                <button
                  className="mt-4 rounded border border-border-2 px-4 py-2 text-[12.5px] font-semibold text-text-secondary hover:bg-bg-3"
                  onClick={() => {
                    setVideo(null);
                    setVideoFile(null);
                  }}
                >
                  Replace Video
                </button>
              </div>
            )}
          </Panel>
        )}

        {step === 2 && video && (
          <Panel title="Step 2 · Select Analysis Modules" meta={`${selectedCount} selected`}>
            {deepLinkNote && (
              <div className="mb-4 flex items-start gap-2 rounded-md border border-accent-blue/30 bg-accent-blue/10 px-3 py-2.5 text-[12px] text-text-secondary">
                <Info size={15} className="mt-0.5 shrink-0 text-accent-blue" />
                {deepLinkNote}
              </div>
            )}
            <div className="flex flex-col gap-3">
              <ModuleCard icon={Eye} title="Target Person ID" description="Identify and continuously track a specific person." selected={modules.person_id} onToggle={() => toggleModule("person_id")} />
              <ModuleCard icon={Search} title="ANPR / Plate Search" description="Detect, read and search vehicle registration plates." selected={modules.anpr} onToggle={() => toggleModule("anpr")} />
              <ModuleCard icon={ShieldAlert} title="Zone Intrusion" description="Detect entry, exit and dwell inside restricted areas." selected={modules.zone} onToggle={() => toggleModule("zone")} />
              <ModuleCard icon={Sparkles} title="Behavioral Analytics" description="Detect loitering, abnormal movement and direction changes." selected={modules.behavior} onToggle={() => toggleModule("behavior")} />
              <ModuleCard icon={Moon} title="Low-Light Enhancement" description="Automatically improve genuinely underexposed footage." selected={modules.lowlight} onToggle={() => toggleModule("lowlight")} />
              <ModuleCard icon={CloudFog} title="Haze / Fog Removal" description="Automatically detect and clear mist, fog or haze obscuring the camera." selected={modules.dehaze} onToggle={() => toggleModule("dehaze")} />
            </div>
          </Panel>
        )}

        {step === 3 && video && (
          <div className="flex flex-col gap-4">
            {modules.person_id && (
              <Panel title="Target Person Configuration">
                <ReferencePhotoUpload onChange={({ referenceSetId, photoCount }) => {
                  setReferenceSetId(referenceSetId);
                  setReferenceCount(photoCount);
                }} />
                {referenceSetId && (
                  <div className="mt-4 grid grid-cols-3 gap-3 border-t border-border-1 pt-4 text-[12px]">
                    <ConfigStat label="Reference Count" value={String(referenceCount)} />
                    <ConfigStat label="Recognition Threshold" value="0.42" />
                    <ConfigStat label="Confirmation" value="Multi-frame" />
                  </div>
                )}
              </Panel>
            )}

            {modules.anpr && (
              <Panel title="ANPR Configuration">
                <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wide text-text-secondary">Plate Search (optional)</label>
                <input
                  className="w-full rounded border border-border-2 bg-bg-3 px-3 py-2.5 font-mono uppercase tracking-widest text-text-primary placeholder:text-text-disabled focus:border-accent-blue focus:outline-none"
                  placeholder="e.g. DL01AB1234"
                  value={targetPlate}
                  onChange={(e) => setTargetPlate(e.target.value)}
                  maxLength={20}
                />
                <p className="mt-2 text-[11.5px] text-text-tertiary">
                  Drishti will search confirmed plate observations in the uploaded video. Leave blank to run general ANPR without searching for a specific plate.
                </p>
              </Panel>
            )}

            {modules.zone && (
              <Panel title="Zone Configuration">
                <ZoneDrawer videoId={video.video_id} zones={zones} onZonesChange={setZones} />
                {zones.length === 0 && (
                  <div className="mt-3 flex items-center gap-2 text-[11.5px] text-accent-amber">
                    <AlertTriangle size={13} /> Draw at least one zone to continue.
                  </div>
                )}
              </Panel>
            )}

            {modules.behavior && (
              <Panel title="Behavioral Analytics Configuration">
                <BehaviorConfigPanel value={behaviorConfig} onChange={setBehaviorConfig} />
              </Panel>
            )}

            {modules.lowlight && (
              <Panel title="Low-Light Enhancement">
                <div className="flex items-center justify-between rounded-md border border-border-1 bg-bg-3 px-4 py-3">
                  <div>
                    <div className="text-[12.5px] font-semibold text-text-primary">Auto Enhancement</div>
                    <p className="mt-1 text-[11.5px] text-text-tertiary">Automatically enhance only footage that requires low-light correction.</p>
                  </div>
                  <span className="rounded-full border border-accent-green/35 bg-accent-green/12 px-2.5 py-1 text-[10.5px] font-semibold text-accent-green">DEFAULT ON</span>
                </div>
              </Panel>
            )}

            {modules.dehaze && (
              <Panel title="Haze / Fog Removal">
                <div className="flex items-center justify-between rounded-md border border-border-1 bg-bg-3 px-4 py-3">
                  <div>
                    <div className="text-[12.5px] font-semibold text-text-primary">Auto Dehazing</div>
                    <p className="mt-1 text-[11.5px] text-text-tertiary">Automatically clear only footage that is genuinely hazy or misty (Dark Channel Prior).</p>
                  </div>
                  <span className="rounded-full border border-accent-green/35 bg-accent-green/12 px-2.5 py-1 text-[10.5px] font-semibold text-accent-green">DEFAULT ON</span>
                </div>
                <p className="mt-3 text-[11.5px] text-text-tertiary">
                  Works well on light-to-moderate haze/mist and can improve detection recall in those conditions. In dense fog, visible-light dehazing has a physical ceiling — it restores contrast, not detail that was never captured by the sensor.
                </p>
              </Panel>
            )}

            <Panel title="Alerts (optional)">
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wide text-text-secondary">Webhook URL</label>
              <input
                className="w-full rounded border border-border-2 bg-bg-3 px-3 py-2.5 font-mono text-[12.5px] text-text-primary placeholder:text-text-disabled focus:border-accent-blue focus:outline-none"
                placeholder="https://hooks.slack.com/services/…"
                value={webhookUrl}
                onChange={(e) => setWebhookUrl(e.target.value)}
              />
              <p className="mt-2 flex items-start gap-2 text-[11.5px] text-text-tertiary">
                <Bell size={13} className="mt-0.5 shrink-0" />
                Sends a JSON POST here when a target is confirmed/reacquired, a predicted zone intrusion fires, or similar target-related alerts occur — works directly with Slack, Discord and Teams incoming webhooks. Leave blank to disable.
              </p>
            </Panel>
          </div>
        )}

        {step === 4 && video && (
          <Panel title="Review & Start">
            <SectionTitle>Video</SectionTitle>
            <VideoSummary filename={video.filename} video={video.video_info} />
            <div className="my-4 h-px bg-border-1" />

            <SectionTitle>Modules Selected</SectionTitle>
            <div className="mb-4 flex flex-wrap gap-2">
              {modules.person_id && <ReviewChip label="Target Person ID" />}
              {modules.anpr && <ReviewChip label={targetPlate ? `ANPR — Search "${targetPlate.toUpperCase()}"` : "ANPR (general)"} />}
              {modules.zone && <ReviewChip label={`Zone Intrusion (${zones.length} zone${zones.length === 1 ? "" : "s"})`} />}
              {modules.behavior && <ReviewChip label="Behavioral Analytics" />}
              {modules.lowlight && <ReviewChip label="Low-Light Enhancement" />}
              {modules.dehaze && <ReviewChip label="Haze / Fog Removal" />}
              {webhookUrl.trim() && <ReviewChip label="Webhook Alerts" />}
              {selectedCount === 0 && <span className="text-[12.5px] text-text-tertiary">No modules selected</span>}
            </div>

            {modules.person_id && (
              <div className="mb-2 text-[12.5px] text-text-secondary">Reference photos: <span className="font-mono text-text-primary">{referenceCount}</span></div>
            )}
            {modules.zone && (
              <div className="mb-2 text-[12.5px] text-text-secondary">
                Zones: <span className="font-mono text-text-primary">{zones.map((z) => z.label).join(", ")}</span>
              </div>
            )}
            <div className="mb-4 text-[12.5px] text-text-secondary">
              Processing mode: <span className="font-mono text-text-primary">Full video · CPU</span>
            </div>

            {submitError && (
              <div className="mb-4 flex items-center gap-2 rounded-md border border-accent-red/35 bg-accent-red/10 px-3 py-2.5 text-[12px] text-accent-red">
                <AlertTriangle size={14} className="shrink-0" /> {submitError}
              </div>
            )}

            <button
              onClick={handleStart}
              disabled={submitting || selectedCount === 0}
              className="w-full rounded-md bg-accent-blue py-3 text-[13.5px] font-bold tracking-wide text-[#051020] transition-colors hover:bg-[#59aeff] disabled:opacity-40"
            >
              {submitting ? "STARTING…" : "START ANALYSIS"}
            </button>
          </Panel>
        )}

        <div className="mt-5 flex justify-between">
          <button
            disabled={step === 1}
            onClick={() => setStep((s) => Math.max(1, s - 1))}
            className="rounded border border-border-2 px-4 py-2 text-[12.5px] font-semibold text-text-secondary hover:bg-bg-3 disabled:opacity-30"
          >
            Back
          </button>
          {step < 4 && (
            <button
              disabled={(step === 1 && !canGoStep2) || (step === 2 && !canGoStep3) || (step === 3 && !canGoStep4)}
              onClick={() => setStep((s) => Math.min(4, s + 1))}
              className="rounded bg-accent-blue px-5 py-2 text-[12.5px] font-bold text-[#051020] hover:bg-[#59aeff] disabled:opacity-40"
            >
              Continue
            </button>
          )}
        </div>
      </PageBody>
    </>
  );
}

function ReviewChip({ label }: { label: string }) {
  return <span className="rounded-full border border-border-2 bg-bg-3 px-3 py-1 text-[11px] font-semibold text-text-secondary">{label}</span>;
}

function ConfigStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-wide text-text-tertiary">{label}</div>
      <div className="mt-0.5 font-mono text-text-primary">{value}</div>
    </div>
  );
}
