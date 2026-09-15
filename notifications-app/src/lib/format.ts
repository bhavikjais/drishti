/** 0 -> "00:00.0", 14.2 -> "00:14.2" - mirrors frontend/src/lib/format.ts's
 * formatTimestamp, which mirrors the backend's own core.output overlay
 * formatting, so timestamps read identically everywhere. */
export function formatTimestamp(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "--:--";
  const s = Math.max(0, seconds);
  const m = Math.floor(s / 60);
  const rem = s - m * 60;
  return `${String(m).padStart(2, "0")}:${rem.toFixed(1).padStart(4, "0")}`;
}
