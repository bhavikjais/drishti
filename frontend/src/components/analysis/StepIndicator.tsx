import { Check } from "lucide-react";

const STEPS = ["Upload Video", "Select Analysis", "Configure", "Review & Start"];

export function StepIndicator({ current }: { current: number }) {
  return (
    <div className="mb-6 flex items-center gap-2">
      {STEPS.map((label, i) => {
        const step = i + 1;
        const state = step < current ? "done" : step === current ? "active" : "pending";
        return (
          <div key={label} className="flex flex-1 items-center gap-2 last:flex-none">
            <div className="flex items-center gap-2 whitespace-nowrap text-[11.5px] font-semibold tracking-wide">
              <span
                className={`flex h-6 w-6 items-center justify-center rounded-full border text-[11px] ${
                  state === "active"
                    ? "border-accent-blue bg-accent-blue text-[#051020]"
                    : state === "done"
                      ? "border-accent-green bg-accent-green/12 text-accent-green"
                      : "border-border-2 bg-bg-3 text-text-secondary"
                }`}
              >
                {state === "done" ? <Check size={13} /> : step}
              </span>
              <span className={state === "pending" ? "text-text-tertiary" : "text-text-primary"}>{label.toUpperCase()}</span>
            </div>
            {step < STEPS.length && <span className="h-px min-w-5 flex-1 bg-border-2" />}
          </div>
        );
      })}
    </div>
  );
}
