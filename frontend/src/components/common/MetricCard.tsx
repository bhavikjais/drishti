import type { LucideIcon } from "lucide-react";

type Accent = "default" | "red" | "amber" | "green" | "blue";

const accentClass: Record<Accent, string> = {
  default: "text-text-primary",
  red: "text-accent-red",
  amber: "text-accent-amber",
  green: "text-accent-green",
  blue: "text-accent-blue",
};

export function MetricCard({
  label,
  value,
  sub,
  accent = "default",
  icon: Icon,
}: {
  label: string;
  value: string | number;
  sub?: string;
  accent?: Accent;
  icon?: LucideIcon;
}) {
  const isEmpty = value === "" || value == null;
  return (
    <div className="rounded-[10px] border border-border-1 bg-bg-2 px-5 py-4">
      <div className="flex items-center gap-1.5 text-[10.5px] font-semibold tracking-wider text-text-tertiary">
        {Icon && <Icon size={12} />}
        {label}
      </div>
      <div className={`mt-2 tabular-nums text-[32px] font-bold leading-none tracking-tight ${isEmpty ? "text-text-disabled" : accentClass[accent]}`}>
        {isEmpty ? "—" : value}
      </div>
      {sub && <div className="mt-1 text-[11px] text-text-tertiary">{sub}</div>}
    </div>
  );
}
