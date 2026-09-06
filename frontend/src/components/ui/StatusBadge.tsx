import { cn } from "@/lib/cn";
import type { ApplicationStatus, InspectionResult } from "@/lib/types";

type Tone = "success" | "warning" | "danger" | "info" | "neutral";

const toneClasses: Record<Tone, string> = {
  success: "bg-success-50 text-success",
  warning: "bg-warning-50 text-warning",
  danger: "bg-danger-50 text-danger",
  info: "bg-info-50 text-info",
  neutral: "bg-neutralx-50 text-neutralx",
};

// Single source of truth: every place in the app that shows an application
// status should render through this map, so "scheduled" always looks the
// same whether it's in a table row, a timeline, or a dashboard stat.
export const APPLICATION_STATUS_TONE: Record<ApplicationStatus, Tone> = {
  submitted: "info",
  scheduled: "warning",
  inspected: "info",
  certified: "success",
  expiring: "warning",
  expired: "danger",
  rejected: "danger",
};

export const APPLICATION_STATUS_LABEL: Record<ApplicationStatus, string> = {
  submitted: "Submitted",
  scheduled: "Scheduled",
  inspected: "Inspected",
  certified: "Certified",
  expiring: "Expiring soon",
  expired: "Expired",
  rejected: "Rejected",
};

export function ApplicationStatusBadge({ status }: { status: ApplicationStatus }) {
  return <Badge tone={APPLICATION_STATUS_TONE[status]}>{APPLICATION_STATUS_LABEL[status]}</Badge>;
}

export function InspectionResultBadge({ result }: { result: InspectionResult }) {
  return <Badge tone={result === "pass" ? "success" : "danger"}>{result === "pass" ? "Pass" : "Fail"}</Badge>;
}

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: React.ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-sm px-2 py-0.5 text-xs font-medium",
        toneClasses[tone],
      )}
    >
      {children}
    </span>
  );
}
