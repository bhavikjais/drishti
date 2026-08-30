import {
  AlertTriangle, Car, Clock, Crosshair, Eye, Footprints, Gauge, MapPin, MapPinOff,
  ShieldAlert, Sparkles, TriangleAlert, type LucideIcon,
} from "lucide-react";

export type Severity = "red" | "amber" | "green" | "blue" | "neutral";

export interface EventMeta {
  label: string;
  severity: Severity;
  icon: LucideIcon;
}

// Every event type the backend actually emits (core/events.py, zone/state.py,
// behavior/state.py, anpr/pipeline.py, orchestrator.py's TARGET_ZONE_INTRUSION
// / LOW_LIGHT). Unknown types fall back to a neutral generic entry rather
// than crashing the UI.
const REGISTRY: Record<string, EventMeta> = {
  TARGET_CONFIRMED: { label: "Target Confirmed", severity: "red", icon: Crosshair },
  TARGET_REACQUIRED: { label: "Target Reacquired", severity: "red", icon: Crosshair },
  TARGET_LOST: { label: "Target Lost", severity: "amber", icon: Eye },
  VEHICLE_DETECTED: { label: "Vehicle Detected", severity: "blue", icon: Car },
  PLATE_DETECTED: { label: "Plate Detected", severity: "blue", icon: Car },
  PLATE_READ: { label: "Plate Read", severity: "blue", icon: Car },
  PLATE_CONFIRMED: { label: "Plate Confirmed", severity: "green", icon: Car },
  TARGET_VEHICLE_FOUND: { label: "Target Vehicle Found", severity: "red", icon: Car },
  TARGET_VEHICLE_REACQUIRED: { label: "Target Vehicle Reacquired", severity: "red", icon: Car },
  TARGET_VEHICLE_LOST: { label: "Target Vehicle Lost", severity: "amber", icon: Car },
  ZONE_ENTRY: { label: "Zone Entry", severity: "amber", icon: MapPin },
  ZONE_EXIT: { label: "Zone Exit", severity: "green", icon: MapPinOff },
  LONG_DWELL: { label: "Long Dwell", severity: "amber", icon: Clock },
  TARGET_ZONE_INTRUSION: { label: "Target Zone Intrusion", severity: "red", icon: ShieldAlert },
  LOITERING: { label: "Loitering", severity: "amber", icon: Footprints },
  SUDDEN_DIRECTION_CHANGE: { label: "Sudden Direction Change", severity: "amber", icon: TriangleAlert },
  ABNORMAL_SPEED: { label: "Abnormal Speed", severity: "amber", icon: Gauge },
  REPEATED_BACK_AND_FORTH: { label: "Repeated Pacing", severity: "amber", icon: Footprints },
  TARGET_BEHAVIOR_ALERT: { label: "Target Behavior Alert", severity: "red", icon: ShieldAlert },
  LOW_LIGHT: { label: "Low-Light Detected", severity: "blue", icon: Sparkles },
};

const FALLBACK: EventMeta = { label: "Event", severity: "neutral", icon: AlertTriangle };

export function eventMeta(type: string): EventMeta {
  return REGISTRY[type] ?? { ...FALLBACK, label: type };
}
