import type { BwEvent, ZoneSummary } from "../api/types";

export interface ZoneIntrusion {
  zoneId: string;
  zoneLabel: string;
  trackId: number;
  entrySec: number;
  exitSec: number | null;
  dwellSec: number | null;
  evidencePath?: string | null;
}

/** The backend's summary.zones only gives aggregate counts (entries/exits/
 * dwell_events per zone) - the per-instance "Track #17 entered at X, exited
 * at Y, dwelled Zs" rows the Results page shows are derived here from the
 * real ZONE_ENTRY/ZONE_EXIT/LONG_DWELL events, matched up per (zone, track)
 * in chronological order. */
export function deriveZoneIntrusions(events: BwEvent[], zones: ZoneSummary[]): ZoneIntrusion[] {
  const labelByZoneId = new Map(zones.map((z) => [z.zone_id, z.label]));
  const open = new Map<string, ZoneIntrusion>();
  const result: ZoneIntrusion[] = [];

  const relevant = events
    .filter((e) => e.zone && ["ZONE_ENTRY", "ZONE_EXIT", "LONG_DWELL"].includes(e.type))
    .sort((a, b) => a.timestamp_sec - b.timestamp_sec);

  for (const ev of relevant) {
    const key = `${ev.zone}:${ev.track_id}`;
    if (ev.type === "ZONE_ENTRY" && ev.track_id != null) {
      const record: ZoneIntrusion = {
        zoneId: ev.zone!,
        zoneLabel: labelByZoneId.get(ev.zone!) ?? "Zone",
        trackId: ev.track_id,
        entrySec: ev.timestamp_sec,
        exitSec: null,
        dwellSec: null,
        evidencePath: ev.evidence_path,
      };
      open.set(key, record);
      result.push(record);
    } else if (ev.type === "LONG_DWELL") {
      const record = open.get(key);
      if (record && typeof ev.data.duration_sec === "number") record.dwellSec = ev.data.duration_sec as number;
    } else if (ev.type === "ZONE_EXIT") {
      const record = open.get(key);
      if (record) {
        record.exitSec = ev.timestamp_sec;
        if (typeof ev.data.dwell_duration_sec === "number") record.dwellSec = ev.data.dwell_duration_sec as number;
        open.delete(key);
      }
    }
  }
  return result;
}
