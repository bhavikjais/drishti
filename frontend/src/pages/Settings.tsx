import { Info } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { PageBody, PageHeader } from "../components/layout/AppLayout";
import { Panel, KeyValueRow } from "../components/common/Panel";

// The backend has no settings-persistence endpoint (no GET/PUT /api/settings) -
// per-analysis thresholds (behavior sensitivity, low-light, etc.) are
// configured on the Analysis page and apply only to that job. Rather than
// build editable controls here that would silently do nothing, this page
// shows the real system defaults for reference and is explicit that it's
// read-only, pointing to where settings actually take effect.
export function Settings() {
  const [tab, setTab] = useState<"basic" | "advanced">("basic");
  const navigate = useNavigate();

  return (
    <>
      <PageHeader title="Settings" subtitle="System defaults and reference configuration" />
      <PageBody narrow>
        <div className="mb-4 flex items-start gap-2 rounded-md border border-accent-blue/30 bg-accent-blue/10 px-4 py-3 text-[12px] text-text-secondary">
          <Info size={16} className="mt-0.5 shrink-0 text-accent-blue" />
          <div>
            These are the BorderWatch system defaults. Module-specific thresholds (loitering sensitivity, low-light
            auto-enhancement, etc.) are configured per-analysis on the{" "}
            <button onClick={() => navigate("/analysis")} className="font-semibold text-accent-blue underline underline-offset-2">
              Analysis page
            </button>{" "}
            and apply only to that job.
          </div>
        </div>

        <div className="mb-4 flex gap-1 rounded-md border border-border-2 bg-bg-3 p-1 w-fit">
          {(["basic", "advanced"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded px-4 py-1.5 text-[12px] font-semibold capitalize transition-colors ${
                tab === t ? "bg-accent-blue text-[#051020]" : "text-text-secondary hover:text-text-primary"
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        <div className="flex flex-col gap-4">
          <Panel title="Processing Preferences">
            <KeyValueRow label="Compute Device" value="Auto-detected (CUDA / CPU)" />
            <KeyValueRow label="Full Video Processing" value="Enabled (no frame cap)" />
            <KeyValueRow label="Video Decoding" value="OpenCV" />
          </Panel>

          <Panel title="Detection Configuration">
            <KeyValueRow label="Face Recognition Threshold" value="0.42" />
            <KeyValueRow label="Minimum Reference Votes" value="2 (adapts to reference count)" />
            <KeyValueRow label="Face Sample Interval" value="Every 5 frames" />
            {tab === "advanced" && (
              <>
                <KeyValueRow label="Target Confirmation Observations" value="2" />
                <KeyValueRow label="Track Gap Tolerance" value="45 frames" />
              </>
            )}
          </Panel>

          <Panel title="ANPR Settings">
            <KeyValueRow label="OCR Engine" value="Tesseract" />
            <KeyValueRow label="Plate Match Threshold" value="0.85 similarity" />
            <KeyValueRow label="Min Confirming Observations" value="3" />
            {tab === "advanced" && (
              <>
                <KeyValueRow label="OCR Sample Interval" value="Every 5 frames" />
                <KeyValueRow label="Min Read Confidence" value="25%" />
              </>
            )}
          </Panel>

          <Panel title="Behavior Thresholds (Defaults)">
            <KeyValueRow label="Loitering Threshold" value="10s" />
            <KeyValueRow label="Direction-Change Sensitivity" value="70°" />
            <KeyValueRow label="Speed Anomaly Threshold" value="400 px/s" />
            {tab === "advanced" && (
              <>
                <KeyValueRow label="Repeated Movement Count" value="3 reversals" />
                <KeyValueRow label="Event Cooldown" value="8s" />
              </>
            )}
          </Panel>

          <Panel title="Low-Light Settings">
            <KeyValueRow label="Detection Trigger" value="Mean brightness < 65" />
            <KeyValueRow label="Backend" value="Fast (CLAHE + Gamma)" />
            {tab === "advanced" && <KeyValueRow label="Shadow Percentile Trigger" value="10th percentile < 25" />}
          </Panel>

          <Panel title="Output Settings">
            <KeyValueRow label="Preferred Codec" value="H.264 (avc1)" />
            <KeyValueRow label="Fallback Codec" value="mp4v" />
            <KeyValueRow label="Resolution" value="Preserved from source" />
            <KeyValueRow label="Frame Rate" value="Preserved from source" />
          </Panel>
        </div>
      </PageBody>
    </>
  );
}
