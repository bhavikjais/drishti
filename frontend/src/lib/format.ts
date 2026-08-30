/** 0 -> "00:00.0", 14.2 -> "00:14.2", 75.3 -> "01:15.3" - mirrors the
 * backend's own core.output.format_timestamp so on-screen timestamps read
 * identically to the burned-in overlay timestamps in the output video. */
export function formatTimestamp(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "--:--";
  const s = Math.max(0, seconds);
  const m = Math.floor(s / 60);
  const rem = s - m * 60;
  return `${String(m).padStart(2, "0")}:${rem.toFixed(1).padStart(4, "0")}`;
}

/** Elapsed-style mm:ss for headers/metrics (no sub-second precision). */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "--:--";
  const s = Math.max(0, Math.round(seconds));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${String(m).padStart(2, "0")}:${String(rem).padStart(2, "0")}`;
}

export function formatPercent(fraction: number | null | undefined, digits = 0): string {
  if (fraction == null || Number.isNaN(fraction)) return "--";
  return `${(fraction * 100).toFixed(digits)}%`;
}

export function formatConfidence(pct: number | null | undefined): string {
  if (pct == null || Number.isNaN(pct)) return "--";
  return `${pct.toFixed(1)}%`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value.toFixed(1)} ${units[i]}`;
}

export function formatResolution(width?: number, height?: number): string {
  if (!width || !height) return "--";
  return `${width}×${height}`;
}

/** Title-cases an UPPER_SNAKE event/type name for display: "ZONE_ENTRY" -> "Zone Entry". */
export function titleCase(value: string): string {
  return value
    .split("_")
    .map((w) => (w.length ? w[0].toUpperCase() + w.slice(1).toLowerCase() : w))
    .join(" ");
}

/** Display-only normalization for plate search input (uppercase, strip
 * spaces/hyphens) - mirrors backend.modules.anpr.ocr.normalize_plate's
 * formatting rules so what the user sees matches what's actually compared
 * server-side. This never rewrites a CONFIRMED plate value returned by the
 * API - it only shapes what the user types into the search box. */
export function normalizePlateForDisplay(raw: string): string {
  return raw.toUpperCase().replace(/[\s-]/g, "");
}
