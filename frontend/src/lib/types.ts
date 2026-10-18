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
  /** How long a certificate for this type is valid when issued today (e.g. "1 year"). */
  validity_days?: number | null;
  validity_label?: string | null;
}

export interface ValidityRule {
  type: string;
  days: number;
  label: string;
  default_days: number;
  is_default: boolean;
  updated_at: string | null;
  updated_by_name: string | null;
}

export interface ValidityRules {
  default_days: number;
  default_label: string;
  min_days: number;
  max_days: number;
  items: ValidityRule[];
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

export type ScheduleSlot = "morning" | "afternoon";

export interface ScheduleHistoryEntry {
  kind: "scheduled" | "rescheduled" | "assigned" | "reassigned";
  date: string;
  slot: ScheduleSlot;
  at: string;
  by?: string | null;
  reason?: string | null;
  previous_date?: string | null;
  previous_slot?: ScheduleSlot | null;
}

export interface ScheduleInput {
  date: string;
  slot: ScheduleSlot;
  reason?: string;
}

export interface SlotAvailability {
  officer_id: string;
  capacity_per_slot: number;
  days: {
    date: string;
    bookable: boolean;
    reason: string | null;
    slots: { slot: ScheduleSlot; label: string; booked: number; capacity: number; available: number }[];
  }[];
}

export interface Application {
  id: string;
  instrument_id: string;
  owner_id: string;
  status: ApplicationStatus;
  assigned_officer_id: string | null;
  // "renewal" = re-verification following an earlier certificate. Absent on old records (= initial).
  application_type?: "initial" | "renewal";
  previous_certificate_id?: string | null;
  previous_cert_no?: string | null;
  previous_valid_until?: string | null; // expiry of the certificate being renewed
  history?: ApplicationHistoryEntry[];
  created_at?: string;
  // Denormalised from the instrument; used to match an application to an officer's jurisdiction.
  state_code?: string;
  district_code?: string;
  // Inspection schedule: an India calendar date (YYYY-MM-DD) and a slot. Null until an officer is assigned.
  scheduled_date?: string | null;
  slot?: ScheduleSlot | null;
  slot_label?: string | null;
  schedule_history?: ScheduleHistoryEntry[];
  // Present on list endpoints that join instrument data server-side.
  // Treat as optional — always fall back to a separate instrument fetch.
  instrument?: Instrument;
}

export type InspectionResult = "pass" | "fail";
export type IdentityMethod = "qr" | "manual";
export interface InspectionLocation {
  lat: number;
  lng: number;
  accuracy_m?: number;
}

// What the officer records per instrument type (served by GET /inspections/form-spec).
export interface InspectionFormSpec {
  form_version: number;
  instrument_type: string;
  test: {
    title: string;
    reference_label: string;
    indicated_label: string;
    min_points: number;
    max_points: number;
    hint: string;
    unit: string;
  };
  checks: { key: string; label: string; required: boolean }[];
  seal: { label: string; required_on_pass: boolean };
}

export interface TestPoint {
  reference: number;
  indicated: number;
}
export interface TestPointResult extends TestPoint {
  error: number; // indicated - reference, worked out by the server
  error_pct: number | null; // of the reference; null when the reference is zero
}
export interface InspectionCheck {
  key: string;
  label: string;
  ok: boolean;
}

export interface Inspection {
  id: string;
  application_id: string;
  officer_id?: string | null; // not sent to owners
  seal_number?: string | null;
  test_points?: TestPointResult[];
  checks?: InspectionCheck[];
  // Null on inspections recorded before the detailed form existed.
  form?: { instrument_type: string; unit: string; test_title: string; reference_label: string; indicated_label: string } | null;
  observations: string;
  result: InspectionResult;
  photos: string[];
  identity_method?: IdentityMethod;
  location?: InspectionLocation | null; // required on submit; optional here for pre-existing records
  submitted_offline?: boolean; // captured on the device before the server received it
  created_at?: string;
}

export interface CertificateSummary {
  id: string;
  cert_no?: string | null;
  seal_number?: string | null; // the stamp / seal number fixed on the instrument
  verified_on: string;
  valid_from?: string; // later than verified_on when a renewal was issued before the old certificate expired
  valid_until: string;
  is_expired: boolean;
}

export interface CertificateVerifyResponse {
  valid: boolean;
  reason?: "not_found";
  certificate?: CertificateSummary;
  // Only on an expired certificate whose instrument has an application in progress.
  reverification?: { in_progress: boolean; status: ApplicationStatus; applied_on: string };
  instrument?: Pick<Instrument, "type" | "manufacturer" | "model" | "uiid">;
  owner?: { org_name: string; location: string };
}

export interface Certificate extends CertificateSummary {
  cert_no?: string | null;
  instrument_id?: string | null;
  renewal_opens_on?: string; // owners may apply for re-verification from this moment
  application_type?: "initial" | "renewal";
  previous_certificate_id?: string | null;
  previous_cert_no?: string | null;
  seal_number?: string | null;
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

// ---- Oversight: pendency ageing, district-wise, enforcement (admin + officers, read-only) ----
export interface PendencyStatusCounts {
  submitted: number;
  scheduled: number;
  inspected: number;
}

export interface PendencyReport {
  generated_at: string;
  target_days: number;
  total_open: number;
  unassigned: number;
  over_target: number;
  by_status: PendencyStatusCounts;
  buckets: { label: string; min_days: number; max_days: number | null; count: number; by_status: PendencyStatusCounts }[];
  oldest: {
    application_id: string;
    uiid: string | null;
    instrument_type: string | null;
    status: ApplicationStatus;
    application_type: string;
    state_name: string | null;
    district_name: string | null;
    submitted_at: string;
    age_days: number;
    assigned: boolean;
  }[];
}

export interface DistrictRow {
  state_code: string;
  state_name: string;
  district_code: string;
  district_name: string;
  instruments: number;
  open_applications: number;
  overdue_applications: number;
  verified: number;
  expired: number;
}

export interface DistrictReport {
  generated_at: string;
  target_days: number;
  totals: Omit<DistrictRow, "state_code" | "state_name" | "district_code" | "district_name">;
  rows: DistrictRow[];
}

export type EnforcementBand = "recent" | "overdue" | "long_overdue";

export interface EnforcementItem {
  instrument_id: string;
  uiid: string | null;
  instrument_type: string | null;
  owner_name: string | null;
  org_name: string | null;
  address_line: string | null;
  state_code: string;
  state_name: string | null;
  district_code: string;
  district_name: string | null;
  cert_no: string | null;
  valid_until: string;
  days_overdue: number;
  band: EnforcementBand;
  reverification: { status: ApplicationStatus; applied_on: string } | null;
  case: CaseRef | null;
}

export interface EnforcementReport {
  generated_at: string;
  summary: {
    lapsed: number;
    reverification_applied: number;
    no_reverification: number;
    recent: number;
    overdue: number;
    long_overdue: number;
  };
  total: number;
  page: number;
  page_size: number;
  truncated: boolean;
  items: EnforcementItem[];
}

// ---- Never-certified instruments ----
export interface UncertifiedItem {
  instrument_id: string;
  uiid: string | null;
  instrument_type: string | null;
  owner_name: string | null;
  org_name: string | null;
  address_line: string | null;
  state_code: string;
  state_name: string | null;
  district_code: string;
  district_name: string | null;
  registered_on: string;
  days_since_registered: number;
  application: { status: ApplicationStatus; applied_on: string } | null;
  case: CaseRef | null;
}

export interface UncertifiedReport {
  generated_at: string;
  grace_days: number;
  summary: { total: number; applied: number; not_applied: number };
  total: number;
  page: number;
  page_size: number;
  truncated: boolean;
  items: UncertifiedItem[];
}

// ---- Enforcement cases (notices and escalation) ----
export type CaseKind = "lapsed" | "never_certified";
export type CaseStatus = "open" | "notice_sent" | "escalated" | "resolved";
export type CaseLevel = "lmo" | "gatc" | "admin";

export interface CaseRef {
  id: string;
  status: CaseStatus;
  level: CaseLevel;
}

export interface CaseListItem {
  id: string;
  kind: CaseKind;
  status: CaseStatus;
  level: CaseLevel;
  instrument: { id: string; uiid: string | null; type: string | null; address_line: string | null };
  owner: { name: string | null; org_name: string | null };
  state_name: string | null;
  district_name: string | null;
  opened_at: string;
  last_notice_at: string | null;
  notice_count: number;
  escalation_due: boolean;
  resolved_at: string | null;
  resolution: "renewed" | "certified" | "closed" | null;
  held_by_me: boolean;
}

export interface CaseEvent {
  at: string;
  action: "opened" | "notice" | "note" | "escalated" | "resolved";
  by_name: string | null; // null = done by the system
  by_role: Role | null;
  text: string | null;
  to_level: CaseLevel | null;
  emailed: boolean | null;
}

export interface CaseDetail extends CaseListItem {
  state_code: string | null;
  district_code: string | null;
  opened_by_name: string | null;
  escalation_after_days: number;
  events: CaseEvent[];
  can: { note: boolean; notice: boolean; escalate: boolean; close: boolean; notice_available_on: string | null };
  cert_no: string | null;
  valid_until: string | null;
  registered_on: string | null;
}

export interface CaseListReport {
  generated_at: string;
  summary: {
    active: number;
    open: number;
    notice_sent: number;
    escalated: number;
    escalation_due: number;
    with_me: number;
    resolved: number;
  };
  total: number;
  page: number;
  page_size: number;
  items: CaseListItem[];
}

export interface OwnerNotice {
  case_id: string;
  kind: CaseKind;
  instrument_id: string;
  uiid: string | null;
  instrument_type: string | null;
  sent_at: string;
  message: string | null;
  issued_by: string;
  notice_count: number;
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
