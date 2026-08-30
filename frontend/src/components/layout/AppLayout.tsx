import type { ReactNode } from "react";
import { Sidebar } from "./Sidebar";

export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-screen grid-cols-[248px_1fr] max-[1366px]:grid-cols-[220px_1fr]">
      <Sidebar />
      <div className="flex min-w-0 flex-col">{children}</div>
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="sticky top-0 z-10 flex h-[60px] shrink-0 items-center justify-between border-b border-border-1 bg-bg-1 px-6">
      <div className="flex flex-col gap-0.5">
        <h1 className="text-[15px] font-semibold text-text-primary">{title}</h1>
        {subtitle && <p className="text-[11px] text-text-tertiary">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  );
}

export function PageBody({ children, narrow }: { children: ReactNode; narrow?: boolean }) {
  return <div className={`flex-1 p-6 max-[1366px]:p-5 ${narrow ? "max-w-[1040px]" : ""}`}>{children}</div>;
}
