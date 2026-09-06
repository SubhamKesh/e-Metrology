import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export function Panel({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn("rounded-lg border border-line bg-white shadow-panel", className)}>{children}</div>
  );
}

export function StatCard({
  label,
  value,
  detail,
  tone = "neutral",
}: {
  label: string;
  value: string | number;
  detail?: string;
  tone?: "neutral" | "success" | "warning" | "danger";
}) {
  const toneText: Record<string, string> = {
    neutral: "text-ink",
    success: "text-success",
    warning: "text-warning",
    danger: "text-danger",
  };
  return (
    <Panel className="p-5">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p className={cn("mt-2 font-display text-3xl tabular", toneText[tone])}>{value}</p>
      {detail && <p className="mt-1 text-sm text-slate-400">{detail}</p>}
    </Panel>
  );
}
