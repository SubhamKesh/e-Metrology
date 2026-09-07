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

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
  org_type: "LMO" | "GATC" | null;
  org_name: string | null;
  contact: string | null;
}

export interface Instrument {
  id: string;
  owner_id: string;
  type: string;
  manufacturer: string;
  model: string;
  capacity: string;
  uiid: string;
  location: string;
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
  application_id?: string;
  qr_url: string;
  pdf_url: string;
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
  by_location: { location: string; count: number }[];
}
