import type { Severity } from "../../lib/eventMeta";

const severityClass: Record<Severity, string> = {
  red: "bg-accent-red/12 text-accent-red border-accent-red/35",
  amber: "bg-accent-amber/12 text-accent-amber border-accent-amber/35",
  green: "bg-accent-green/12 text-accent-green border-accent-green/35",
  blue: "bg-accent-blue/10 text-accent-blue border-accent-blue/35",
  neutral: "bg-bg-3 text-text-secondary border-border-2",
};

const dotClass: Record<Severity, string> = {
  red: "bg-accent-red",
  amber: "bg-accent-amber",
  green: "bg-accent-green",
  blue: "bg-accent-blue",
  neutral: "bg-text-tertiary",
};

export function StatusBadge({ label, severity, pulse }: { label: string; severity: Severity; pulse?: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-[3px] text-[11px] font-semibold tracking-wide ${severityClass[severity]}`}>
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dotClass[severity]} ${pulse ? "animate-pulse" : ""}`} />
      {label}
    </span>
  );
}

const JOB_STATUS_SEVERITY: Record<string, Severity> = {
  pending: "neutral",
  running: "blue",
  done: "green",
  failed: "red",
  cancelled: "amber",
};

export function JobStatusBadge({ status }: { status: string }) {
  const severity = JOB_STATUS_SEVERITY[status] ?? "neutral";
  return <StatusBadge label={status.toUpperCase()} severity={severity} pulse={status === "running"} />;
}

const HEALTH_SEVERITY: Record<string, Severity> = { READY: "green", WARNING: "amber", ERROR: "red" };

export function HealthBadge({ state }: { state: "READY" | "WARNING" | "ERROR" }) {
  return <StatusBadge label={state} severity={HEALTH_SEVERITY[state]} />;
}
