import { AlertTriangle, type LucideIcon, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-16 text-center text-text-tertiary">
      <Icon size={32} className="mb-2 opacity-50" />
      <div className="text-[15px] font-semibold text-text-secondary">{title}</div>
      {description && <div className="max-w-[360px] text-[12.5px]">{description}</div>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-16 text-center">
      <AlertTriangle size={32} className="mb-2 text-accent-red opacity-80" />
      <div className="text-[15px] font-semibold text-text-secondary">Unable to load data</div>
      <div className="max-w-[400px] text-[12.5px] text-text-tertiary">{message}</div>
      {onRetry && (
        <button className="btn btn-sm mt-3 inline-flex items-center gap-2 rounded border border-border-2 bg-bg-3 px-3 py-1.5 text-xs font-semibold hover:bg-bg-4" onClick={onRetry}>
          <RefreshCw size={13} /> Retry
        </button>
      )}
    </div>
  );
}

export function LoadingBlock({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-16 text-text-tertiary">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-border-2 border-t-accent-blue" />
      <div className="text-[12.5px]">{label}</div>
    </div>
  );
}

export function SkeletonRow({ className = "" }: { className?: string }) {
  return <div className={`skeleton h-4 rounded ${className}`} />;
}

export function SkeletonCard() {
  return (
    <div className="rounded-[10px] border border-border-1 bg-bg-2 px-5 py-4">
      <SkeletonRow className="mb-3 w-1/2" />
      <SkeletonRow className="h-8 w-1/3" />
    </div>
  );
}
