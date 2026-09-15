import { Cpu, Database } from "lucide-react";
import { getSystemStatus } from "../api/system";
import { PageBody, PageHeader } from "../components/layout/AppLayout";
import { Panel } from "../components/common/Panel";
import { ErrorState, LoadingBlock } from "../components/common/States";
import { HealthBadge } from "../components/common/StatusBadge";
import { useApi } from "../hooks/useApi";
import type { SystemStatus } from "../api/types";

type Health = "READY" | "WARNING" | "ERROR";

function deriveComponents(status: SystemStatus): { label: string; state: Health; detail?: string }[] {
  const models = status.models_present;
  return [
    { label: "API", state: "READY" },
    { label: "Target Recognition (YuNet + SFace)", state: models.yunet && models.sface ? "READY" : "ERROR" },
    { label: "Vehicle / Person Detection (YOLO)", state: models.yolo ? "READY" : "ERROR" },
    { label: "ANPR / OCR Engine", state: status.ocr_available ? "READY" : "WARNING", detail: status.ocr_available ? undefined : String(status.ocr_status?.reason ?? "OCR engine unavailable") },
    { label: "Tracking Engine (ByteTrack)", state: models.yolo ? "READY" : "ERROR" },
    { label: "Zone Engine", state: "READY" },
    { label: "Behavior Engine", state: "READY" },
    { label: "Low-Light Enhancement", state: "READY" },
    { label: "Video Encoder", state: "READY" },
  ];
}

export function SystemStatusPage() {
  const { status, data, error, refetch } = useApi(getSystemStatus);

  return (
    <>
      <PageHeader title="System Status" subtitle="Drishti backend health" />
      <PageBody narrow>
        {status === "loading" && <LoadingBlock label="Checking system status…" />}
        {status === "error" && <ErrorState message={error} onRetry={refetch} />}
        {status === "success" && (
          <div className="flex flex-col gap-4">
            <Panel title="Component Health">
              <div className="flex flex-col divide-y divide-border-1">
                {deriveComponents(data).map((c) => (
                  <div key={c.label} className="flex items-center justify-between py-3 first:pt-0 last:pb-0">
                    <div>
                      <div className="text-[12.5px] font-semibold text-text-primary">{c.label}</div>
                      {c.detail && <div className="mt-0.5 text-[11px] text-text-tertiary">{c.detail}</div>}
                    </div>
                    <HealthBadge state={c.state} />
                  </div>
                ))}
              </div>
            </Panel>

            <div className="grid grid-cols-2 gap-4">
              <Panel title="Compute">
                <div className="flex items-center gap-3">
                  <Cpu size={20} className="text-accent-blue" />
                  <div>
                    <div className="font-mono text-[15px] font-bold uppercase text-text-primary">{data.device}</div>
                    <div className="text-[11px] text-text-tertiary">Inference device</div>
                  </div>
                </div>
              </Panel>
              <Panel title="Job Queue">
                <div className="flex items-center gap-3">
                  <Database size={20} className="text-accent-blue" />
                  <div>
                    <div className="font-mono text-[15px] font-bold text-text-primary">{data.active_jobs} active / {data.total_jobs} total</div>
                    <div className="text-[11px] text-text-tertiary">In-process job queue</div>
                  </div>
                </div>
              </Panel>
            </div>

            <Panel title="OCR Engine Detail">
              <pre className="overflow-x-auto rounded-md bg-bg-0 p-3 text-[11.5px] text-text-secondary">{JSON.stringify(data.ocr_status, null, 2)}</pre>
            </Panel>
          </div>
        )}
      </PageBody>
    </>
  );
}
