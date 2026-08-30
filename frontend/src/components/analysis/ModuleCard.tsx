import type { LucideIcon } from "lucide-react";

export function ModuleCard({
  icon: Icon,
  title,
  description,
  selected,
  onToggle,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  selected: boolean;
  onToggle: () => void;
}) {
  return (
    <div
      role="button"
      onClick={onToggle}
      className={`flex cursor-pointer items-start gap-4 rounded-[10px] border px-5 py-4 transition-colors ${
        selected ? "border-accent-blue bg-accent-blue/10" : "border-border-1 bg-bg-2 hover:border-border-2"
      }`}
    >
      <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-md ${selected ? "bg-accent-blue/20 text-accent-blue" : "bg-bg-4 text-accent-blue"}`}>
        <Icon size={19} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-[13.5px] font-semibold text-text-primary">{title}</div>
        <div className="mt-0.5 text-[11.5px] leading-relaxed text-text-tertiary">{description}</div>
      </div>
      <span
        className={`relative h-[22px] w-[38px] shrink-0 rounded-full border transition-colors ${
          selected ? "border-accent-blue bg-accent-blue" : "border-border-2 bg-bg-4"
        }`}
      >
        <span
          className={`absolute top-[2px] h-[16px] w-[16px] rounded-full transition-transform ${
            selected ? "translate-x-[16px] bg-[#06101f]" : "translate-x-[2px] bg-text-tertiary"
          }`}
        />
      </span>
    </div>
  );
}
