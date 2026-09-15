import {
  AlertTriangle, Car, Clock, CloudFog, Crosshair, Eye, Footprints, Gauge, MapPin, MapPinOff,
  ShieldAlert, Sparkles, TriangleAlert, type LucideIcon,
} from "lucide-react";

// Mirrors frontend/src/lib/eventMeta.ts - kept as a plain copy rather than a
// shared package since this is a deliberately standalone app (own
// build/deploy, no monorepo workspace wiring). Keep the two in sync by hand
// if a new event type is added on the backend.
export type Severity = "red" | "amber" | "green" | "blue" | "neutral";

export interface EventMeta {
  label: string;
  severity: Severity;
  icon: LucideIcon;
}

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
  PREDICTED_ZONE_CROSSING: { label: "Crossing Predicted", severity: "amber", icon: Crosshair },
  TARGET_ZONE_INTRUSION_PREDICTED: { label: "Target Intrusion Predicted", severity: "red", icon: ShieldAlert },
  LOITERING: { label: "Loitering", severity: "amber", icon: Footprints },
  SUDDEN_DIRECTION_CHANGE: { label: "Sudden Direction Change", severity: "amber", icon: TriangleAlert },
  ABNORMAL_SPEED: { label: "Abnormal Speed", severity: "amber", icon: Gauge },
  REPEATED_BACK_AND_FORTH: { label: "Repeated Pacing", severity: "amber", icon: Footprints },
  TARGET_BEHAVIOR_ALERT: { label: "Target Behavior Alert", severity: "red", icon: ShieldAlert },
  LOW_LIGHT: { label: "Low-Light Detected", severity: "blue", icon: Sparkles },
  HAZE_DETECTED: { label: "Haze Detected", severity: "blue", icon: CloudFog },
};

const FALLBACK: EventMeta = { label: "Event", severity: "neutral", icon: AlertTriangle };

export function eventMeta(type: string): EventMeta {
  return REGISTRY[type] ?? { ...FALLBACK, label: type };
}

export type Feature = "person_id" | "zone" | "anpr" | "behavior" | "lowlight" | "dehaze" | "other";

export const FEATURE_LABELS: Record<Feature, string> = {
  person_id: "Target ID",
  zone: "Zone Intrusion",
  anpr: "ANPR",
  behavior: "Behavior",
  lowlight: "Low-Light",
  dehaze: "Haze / Fog",
  other: "Other",
};

const FEATURE_BY_TYPE: Record<string, Feature> = {
  TARGET_CONFIRMED: "person_id", TARGET_REACQUIRED: "person_id", TARGET_LOST: "person_id",
  TARGET_VEHICLE_FOUND: "person_id", TARGET_VEHICLE_REACQUIRED: "person_id", TARGET_VEHICLE_LOST: "person_id",
  ZONE_ENTRY: "zone", ZONE_EXIT: "zone", LONG_DWELL: "zone",
  PREDICTED_ZONE_CROSSING: "zone", TARGET_ZONE_INTRUSION: "zone", TARGET_ZONE_INTRUSION_PREDICTED: "zone",
  VEHICLE_DETECTED: "anpr", PLATE_DETECTED: "anpr", PLATE_READ: "anpr", PLATE_CONFIRMED: "anpr",
  LOITERING: "behavior", SUDDEN_DIRECTION_CHANGE: "behavior", ABNORMAL_SPEED: "behavior",
  REPEATED_BACK_AND_FORTH: "behavior", TARGET_BEHAVIOR_ALERT: "behavior",
  LOW_LIGHT: "lowlight",
  HAZE_DETECTED: "dehaze",
};

export function eventFeature(type: string): Feature {
  return FEATURE_BY_TYPE[type] ?? "other";
}

export function isNotifiable(type: string): boolean {
  return eventMeta(type).severity !== "green";
}
