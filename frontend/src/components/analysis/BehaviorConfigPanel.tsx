import { ChevronDown } from "lucide-react";
import { useState } from "react";

export interface BehaviorConfigValues {
  loitering_seconds: number;
  direction_change_degrees: number;
  speed_threshold_px_per_sec: number;
  reversal_count: number;
  loitering_radius_px: number;
  reversal_angle_degrees: number;
  acceleration_threshold_px_per_sec: number;
  behavior_cooldown_seconds: number;
}

export const DEFAULT_BEHAVIOR_CONFIG: BehaviorConfigValues = {
  loitering_seconds: 10,
  direction_change_degrees: 70,
  speed_threshold_px_per_sec: 400,
  reversal_count: 3,
  loitering_radius_px: 60,
  reversal_angle_degrees: 120,
  acceleration_threshold_px_per_sec: 500,
  behavior_cooldown_seconds: 8,
};

function Slider({
  label,
  value,
  min,
  max,
  step = 1,
  unit,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  unit: string;
  onChange: (v: number) => void;
}) {
  return (
    <div className="mb-4">
      <div className="mb-1.5 flex items-center justify-between text-[12px]">
        <span className="font-semibold text-text-secondary">{label}</span>
        <span className="font-mono text-text-primary">
          {value}
          {unit}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-accent-blue"
      />
    </div>
  );
}

export function BehaviorConfigPanel({ value, onChange }: { value: BehaviorConfigValues; onChange: (v: BehaviorConfigValues) => void }) {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const set = <K extends keyof BehaviorConfigValues>(key: K, v: number) => onChange({ ...value, [key]: v });

  return (
    <div>
      <Slider label="Loitering Threshold" value={value.loitering_seconds} min={3} max={30} unit="s" onChange={(v) => set("loitering_seconds", v)} />
      <Slider
        label="Direction-Change Sensitivity"
        value={130 - value.direction_change_degrees}
        min={10}
        max={90}
        unit="°"
        onChange={(v) => set("direction_change_degrees", 130 - v)}
      />
      <Slider label="Speed Anomaly Threshold" value={value.speed_threshold_px_per_sec} min={100} max={1000} step={50} unit=" px/s" onChange={(v) => set("speed_threshold_px_per_sec", v)} />
      <Slider label="Repeated Movement Count" value={value.reversal_count} min={2} max={6} unit=" reversals" onChange={(v) => set("reversal_count", v)} />

      <button
        onClick={() => setAdvancedOpen((o) => !o)}
        className="mt-1 flex items-center gap-1.5 text-[11.5px] font-semibold text-accent-blue"
      >
        <ChevronDown size={13} className={`transition-transform ${advancedOpen ? "rotate-180" : ""}`} />
        Advanced Settings
      </button>

      {advancedOpen && (
        <div className="mt-3 rounded-md border border-border-1 bg-bg-3 p-3">
          <Slider label="Loitering Radius" value={value.loitering_radius_px} min={20} max={200} step={5} unit=" px" onChange={(v) => set("loitering_radius_px", v)} />
          <Slider label="Reversal Angle" value={value.reversal_angle_degrees} min={90} max={180} unit="°" onChange={(v) => set("reversal_angle_degrees", v)} />
          <Slider label="Acceleration Threshold" value={value.acceleration_threshold_px_per_sec} min={100} max={1000} step={50} unit=" px/s²" onChange={(v) => set("acceleration_threshold_px_per_sec", v)} />
          <Slider label="Event Cooldown" value={value.behavior_cooldown_seconds} min={1} max={30} unit="s" onChange={(v) => set("behavior_cooldown_seconds", v)} />
        </div>
      )}
    </div>
  );
}
