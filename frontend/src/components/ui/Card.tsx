import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/cn";

export function Panel({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn("rounded-xl border border-line bg-white shadow-panel", className)}>{children}</div>
  );
}

type Tone = "neutral" | "success" | "warning" | "danger" | "info";

const toneText: Record<Tone, string> = {
  neutral: "text-ink",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
  info: "text-info",
};
const toneBar: Record<Tone, string> = {
  neutral: "bg-slate-100",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  info: "bg-info",
};

export function StatCard({
  label,
  value,
  detail,
  tone = "neutral",
  to,
}: {
  label: string;
  value: string | number;
  detail?: string;
  tone?: Tone;
  to?: string;
}) {
  const body = (
    <div className="relative overflow-hidden p-4 sm:p-5">
      <span className={cn("absolute inset-y-0 left-0 w-1", toneBar[tone])} aria-hidden="true" />
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={cn("mt-2 font-display text-3xl tabular sm:text-4xl", toneText[tone])}>{value}</p>
      {detail && <p className="mt-1 text-sm text-slate-500">{detail}</p>}
    </div>
  );
  if (to) {
    return (
      <Link
        to={to}
        className="block rounded-xl border border-line bg-white shadow-panel transition-shadow hover:shadow-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal/40"
      >
        {body}
      </Link>
    );
  }
  return <Panel>{body}</Panel>;
}

/** Dashboard quick-action tile. Whole tile is the link. */
export function ActionCard({
  to,
  title,
  description,
  badge,
  primary,
}: {
  to: string;
  title: string;
  description: string;
  badge?: ReactNode;
  primary?: boolean;
}) {
  return (
    <Link
      to={to}
      className={cn(
        "group flex min-h-[5.5rem] flex-col justify-between gap-2 rounded-xl border p-4 shadow-panel transition-shadow hover:shadow-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal/40 sm:p-5",
        primary ? "border-teal bg-teal-50" : "border-line bg-white",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <p className="font-medium text-ink">{title}</p>
        {badge}
      </div>
      <p className="text-sm text-slate-600">{description}</p>
      <span className="text-sm font-medium text-teal transition-transform group-hover:translate-x-0.5" aria-hidden="true">
        Open →
      </span>
    </Link>
  );
}

/** Shared dashboard welcome banner: role chip + greeting + optional action. */
export function DashboardHero({
  roleLabel,
  title,
  description,
  action,
}: {
  roleLabel: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-4 rounded-xl border border-line bg-white p-5 shadow-panel sm:flex-row sm:items-center sm:justify-between sm:p-6">
      <div className="min-w-0">
        <span className="inline-flex rounded-sm bg-brass-50 px-2 py-0.5 text-xs font-medium text-brass-600">
          {roleLabel}
        </span>
        <h1 className="mt-2 break-words font-display text-2xl text-ink sm:text-3xl">{title}</h1>
        <p className="mt-1 text-sm text-slate-600">{description}</p>
      </div>
      {action && <div className="shrink-0 [&>*]:w-full sm:[&>*]:w-auto">{action}</div>}
    </div>
  );
}

export function SectionTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-3 mt-8 flex items-baseline justify-between gap-3">
      <h2 className="font-display text-lg text-ink">{children}</h2>
      {aside}
    </div>
  );
}
