import { Badge } from "@/components/ui/StatusBadge";
import type { CaseKind, CaseLevel, CaseStatus } from "@/lib/types";

export const CASE_STATUS_LABEL: Record<CaseStatus, string> = {
  open: "Case open",
  notice_sent: "Notice sent",
  escalated: "Escalated",
  resolved: "Resolved",
};

const CASE_STATUS_TONE: Record<CaseStatus, "info" | "warning" | "danger" | "success"> = {
  open: "info",
  notice_sent: "warning",
  escalated: "danger",
  resolved: "success",
};

export const LEVEL_LABEL: Record<CaseLevel, string> = {
  lmo: "LMO",
  gatc: "GATC",
  admin: "Admin",
};

export const KIND_LABEL: Record<CaseKind, string> = {
  lapsed: "Lapsed certificate",
  never_certified: "Never certified",
};

export const RESOLUTION_LABEL: Record<string, string> = {
  renewed: "Certificate renewed",
  certified: "Instrument certified",
  closed: "Closed by an officer",
};

export function CaseStatusBadge({ status }: { status: CaseStatus }) {
  return <Badge tone={CASE_STATUS_TONE[status]}>{CASE_STATUS_LABEL[status]}</Badge>;
}

export function LevelBadge({ level }: { level: CaseLevel }) {
  return <Badge tone="neutral">With {LEVEL_LABEL[level]}</Badge>;
}
