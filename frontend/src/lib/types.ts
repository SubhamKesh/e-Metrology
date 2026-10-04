// Domain types mirror the MaapSetu API contract exactly (see /docs/api-contract.md
// in the backend repo). Do not add fields the API doesn't return — if the UI needs
// something the API doesn't expose yet, that's a backend conversation, not a guess.

export type Role = "owner" | "lmo" | "gatc" | "admin";

export const ROLE_LABEL: Record<Role, string> = {
  owner: "Business / User",
  lmo: "Legal Metrology Officer",
  gatc: "GATC",
  admin: "Super Admin",
};

export interface Jurisdiction {
  state_code: string;
  district_code: string | null;
}

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
  status: "pending" | "active" | "rejected";
  org_type: "LMO" | "GATC" | null;
  org_name: string | null;
  contact: string | null;
  jurisdiction: Jurisdiction | null;
  // True for an admin-created officer account that's still on its
  // one-time temp password — the UI should route them to change it
  // before anything else.
  must_change_password: boolean;
  // Whether two-step verification (authenticator app) is set up. Officer and
  // admin accounts must have it; the admin's officer list shows who still has to enrol.
  mfa_enabled: boolean;
}

export interface Location {
  state_code: string;
  district_code: string;
  address_line: string;
}

export interface Instrument {
  id: string;
  owner_id: string;
  type: string;
  manufacturer: string;
  model: string;
  capacity: string;
  serial_no: string;
  uiid: string;
  location: Location;
}

export interface StateOption {
  code: string;
  name: string;
  type: "state" | "ut";
}

export interface DistrictOption {
  code: string;
  name: string;
  state_code: string;
}

export interface InstrumentTypeSpec {
  type: string;
  unit: string;
  input_type: string;
  step: string;
  placeholder: string;
}

// The full lifecycle as enforced by app/services/status_transition.py.
export type ApplicationStatus =
  | "submitted"
  | "scheduled"
  | "inspected"
  | "certified"
  | "expiring"
  | "expired"
  | "rejected";

export interface ApplicationHistoryEntry {
  status: ApplicationStatus;
  at: string;
  by?: string;
  note?: string;
}

export interface Application {
  id: string;
  instrument_id: string;
  owner_id: string;
  status: ApplicationStatus;
  assigned_officer_id: string | null;
  history?: ApplicationHistoryEntry[];
  created_at?: string;
  // Present on list endpoints that join instrument data server-side.
  // Treat as optional — always fall back to a separate instrument fetch.
  instrument?: Instrument;
}

export type InspectionResult = "pass" | "fail";

export interface Inspection {
  id: string;
  application_id: string;
  observations: string;
  result: InspectionResult;
  photos: string[];
  created_at?: string;
}

export interface CertificateSummary {
  id: string;
  verified_on: string;
  valid_until: string;
  is_expired: boolean;
}

export interface CertificateVerifyResponse {
  valid: boolean;
  reason?: "not_found";
  certificate?: CertificateSummary;
  instrument?: Pick<Instrument, "type" | "manufacturer" | "model" | "uiid">;
  owner?: { org_name: string; location: string };
}

export interface Certificate extends CertificateSummary {
  cert_no?: string | null;
  application_id?: string;
  instrument?: {
    type: string | null;
    uiid: string | null;
    manufacturer: string | null;
    model: string | null;
    location: string | null;
  } | null;
  // Null when the PDF could not be produced (or has not been yet).
  qr_url: string | null;
  pdf_url: string | null;
  // True when the PDF is stored by the API itself (no external pdf_url); download it via the API.
  has_pdf?: boolean;
}

// A certified application whose certificate hasn't been generated yet (or failed to generate).
export interface PendingCertificate {
  application_id: string;
  instrument: { type: string | null; uiid: string | null } | null;
  failed: boolean;
}

export interface OwnerDashboard {
  total_instruments: number;
  verified: number;
  pending: number;
  expired: number;
  next_expiry: {
    instrument_type: string;
    uiid: string;
    valid_until: string;
    days_remaining: number;
  } | null;
}

export interface OfficerDashboard {
  assigned: number;
  pending: number;
  completed: number;
  today_inspections: number;
}

export interface AdminDashboard {
  total_instruments: number;
  verified: number;
  pending: number;
  expired: number;
  by_location: { state_code: string; state_name: string; count: number }[];
}

// ---- Security audit log (admin only; read-only) ----
export type AuditOutcome = "success" | "failure" | "blocked" | "ignored";

export interface AuditLogEntry {
  id: string;
  event: string;
  outcome: AuditOutcome;
  email: string | null;
  user_id: string | null;
  role: string | null;
  actor_id: string | null;
  actor_email: string | null;
  ip: string | null;
  user_agent: string | null;
  detail: string | null;
  created_at: string; // ISO 8601, UTC
}

export interface AuditLogPage {
  items: AuditLogEntry[];
  total: number;
  page: number;
  page_size: number;
  events: string[]; // every event name that can appear, for the filter
}
