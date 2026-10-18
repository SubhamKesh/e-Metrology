import { APPLICATION_STATUS_LABEL } from "@/components/ui/StatusBadge";

export const ANY = { value: "", label: "Any" };

export const APPLICATION_STATUS_OPTIONS = [
  ANY,
  ...Object.entries(APPLICATION_STATUS_LABEL).map(([value, label]) => ({ value, label })),
];

export const APPLICATION_TYPE_OPTIONS = [
  ANY,
  { value: "initial", label: "First verification" },
  { value: "renewal", label: "Re-verification" },
];

export const CERTIFICATE_STATUS_OPTIONS = [
  ANY,
  { value: "valid", label: "Valid" },
  { value: "expiring", label: "Valid, expiring soon" },
  { value: "expired", label: "Expired" },
];
