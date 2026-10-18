import { api, downloadFile, fetchBlob } from "./api";
import type {
  AdminDashboard,
  Application,
  ScheduleInput,
  SlotAvailability,
  Certificate,
  CertificateVerifyResponse,
  PendingCertificate,
  DistrictOption,
  Inspection,
  InspectionFormSpec,
  Instrument,
  InstrumentTypeSpec,
  OfficerDashboard,
  OwnerDashboard,
  Role,
  StateOption,
  User,
  AuditLogPage,
} from "./types";

// Builds "?a=1&b=2" from the filters that have a value (empty strings, undefined and false are left out).
export function toQuery(params?: object): string {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value === undefined || value === null || value === "" || value === false) continue;
    usp.set(key, String(value));
  }
  const qs = usp.toString();
  return qs ? `?${qs}` : "";
}

// Search filters. All optional; the server combines them with AND and never widens what a role may see.
export interface ApplicationFilters {
  q?: string;
  status?: string;
  application_type?: string;
  instrument_type?: string;
  state_code?: string;
  district_code?: string;
  date_from?: string; // YYYY-MM-DD, India day
  date_to?: string;
}
export interface CertificateFilters {
  q?: string;
  status?: string; // valid | expiring | expired
  application_type?: string;
  instrument_type?: string;
  date_from?: string;
  date_to?: string;
}
export interface InstrumentFilters {
  owner_id?: string;
  q?: string;
  type?: string;
  state_code?: string;
  district_code?: string;
}

// ---- Auth ----
export interface RegisterPayload {
  name: string;
  email: string;
  password: string;
  role: Role;
  org_type: "LMO" | "GATC" | null;
  org_name?: string;
  contact?: string;
}
export interface AuthResponse {
  user: User;
  token: string;
  // Whether "Remember me" was actually applied. The server only honours it
  // for business/owner accounts, never for officers or admin.
  remember_me?: boolean;
}

// change-password signs the account out of every session, then issues a
// fresh one for this device — so the response also carries a new token.
export type ChangePasswordResponse = User & { token: string; remember_me: boolean };

// /auth/login and /auth/mfa/* answer with either a finished session
// (user + token) or — for officer/admin accounts whose password was accepted
// but who still owe the second step — just an mfa_token saying which step is next.
export interface LoginResponse {
  user: User | null;
  token: string | null;
  remember_me: boolean;
  mfa_required: boolean;
  mfa_setup_required: boolean;
  mfa_token: string | null;
  recovery_codes: string[] | null;
  recovery_codes_remaining: number | null;
}

export interface MfaSetup {
  secret: string;
  otpauth_uri: string;
  qr_data_uri: string;
}

export const AuthApi = {
  register: (body: RegisterPayload) => api.post<AuthResponse>("/auth/register", body, { public: true }),
  login: (body: { email: string; password: string; remember_me?: boolean }) =>
    api.post<LoginResponse>("/auth/login", body, { public: true }),
  mfaSetup: (mfa_token: string) => api.post<MfaSetup>("/auth/mfa/setup", { mfa_token }, { public: true }),
  mfaConfirmSetup: (body: { mfa_token: string; code: string }) =>
    api.post<LoginResponse>("/auth/mfa/confirm-setup", body, { public: true }),
  mfaVerify: (body: { mfa_token: string; code: string }) =>
    api.post<LoginResponse>("/auth/mfa/verify", body, { public: true }),
  // The backend returns the user object directly (not wrapped in {user}).
  me: () => api.get<User>("/auth/me"),
  forgotPassword: (body: { email: string }) =>
    api.post<{ sent: boolean }>("/auth/forgot-password", body, { public: true }),
  resetPassword: (body: { email: string; code: string; new_password: string }) =>
    api.post<{ reset: boolean }>("/auth/reset-password", body, { public: true }),
  logout: () => api.post<void>("/auth/logout"),
  changePassword: (body: { current_password: string; new_password: string }) =>
    api.post<ChangePasswordResponse>("/auth/change-password", body),
};

// ---- Admin: security audit log (read-only) ----
export interface AuditLogQuery {
  event?: string;
  outcome?: string;
  role?: string;
  search?: string;
  date_from?: string; // YYYY-MM-DD
  date_to?: string; // YYYY-MM-DD
  page?: number;
  page_size?: number;
}

export const AdminAuditApi = {
  list: (query: AuditLogQuery = {}) => {
    const usp = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== "") usp.set(key, String(value));
    }
    const qs = usp.toString();
    return api.get<AuditLogPage>(`/admin/audit-logs${qs ? `?${qs}` : ""}`);
  },
};

// ---- Admin: officer accounts (invite-only lmo/gatc) ----
export interface CreateOfficerPayload {
  name: string;
  email: string;
  role: "lmo" | "gatc";
  org_name?: string;
  contact?: string;
  jurisdiction: { state_code: string; district_code: string | null };
}
export interface CreateOfficerResponse {
  user: User;
  temp_password: string;
  emailed: boolean;
}

export const AdminUsersApi = {
  listOfficers: (params?: { q?: string; role?: string; status?: string }) =>
    api.get<User[]>(`/admin/users${toQuery(params)}`),
  listPending: () => api.get<User[]>("/admin/users/pending"),
  createOfficer: (body: CreateOfficerPayload) =>
    api.post<CreateOfficerResponse>("/admin/users/create-officer", body),
  approve: (id: string) => api.post<User>(`/admin/users/${id}/approve`),
  reject: (id: string) => api.post<User>(`/admin/users/${id}/reject`),
  // Officers can't use the self-service "forgot password"; an admin resets it here.
  resetPassword: (id: string) => api.post<CreateOfficerResponse>(`/admin/users/${id}/reset-password`),
  // Clears an officer's authenticator so they can enrol a new one at next sign-in.
  resetMfa: (id: string) => api.post<User>(`/admin/users/${id}/reset-mfa`),
  // LMO -> one district, GATC -> whole state (district_code null).
  changeJurisdiction: (id: string, jurisdiction: { state_code: string; district_code: string | null }) =>
    api.patch<User>(`/admin/users/${id}/jurisdiction`, jurisdiction),
};

// ---- Instruments ----
export const InstrumentApi = {
  create: (body: Omit<Instrument, "id" | "owner_id" | "uiid">) => api.post<Instrument>("/instruments", body),
  list: (params?: InstrumentFilters) => api.get<Instrument[]>(`/instruments${toQuery(params)}`),
  get: (id: string) => api.get<Instrument>(`/instruments/${id}`),
  typeSpecs: () => api.get<InstrumentTypeSpec[]>("/instruments/meta/types"),
};

// ---- Geography (states/districts reference data) ----
export const GeoApi = {
  states: () => api.get<StateOption[]>("/geo/states"),
  districts: (stateCode: string) => api.get<DistrictOption[]>(`/geo/states/${encodeURIComponent(stateCode)}/districts`),
};

// ---- Applications ----
export const ApplicationApi = {
  create: (body: { instrument_id: string; previous_certificate_id?: string }) => api.post<Application>("/applications", body),
  list: (params?: ApplicationFilters & { mine?: boolean }) => api.get<Application[]>(`/applications${toQuery(params)}`),
  get: (id: string) => api.get<Application>(`/applications/${id}`),
  // Claiming books the inspection, so a date and slot are required.
  claim: (id: string, body: ScheduleInput) => api.post<Application>(`/applications/${id}/claim`, body),
  schedule: (id: string, body: ScheduleInput) => api.post<Application>(`/applications/${id}/schedule`, body),
  assign: (id: string, body: ScheduleInput & { officer_id: string }) =>
    api.post<Application>(`/applications/${id}/assign`, body),
  slots: (params: { officer_id?: string; start?: string; days?: number }) => {
    const usp = new URLSearchParams();
    if (params.officer_id) usp.set("officer_id", params.officer_id);
    if (params.start) usp.set("start", params.start);
    if (params.days) usp.set("days", String(params.days));
    const qs = usp.toString();
    return api.get<SlotAvailability>(`/applications/slots${qs ? `?${qs}` : ""}`);
  },
};

// ---- Inspections ----
export const InspectionApi = {
  create: (body: {
    application_id: string;
    observations: string;
    result: "pass" | "fail";
    photos: string[];
    identity_method?: "qr" | "manual";
    location: { lat: number; lng: number; accuracy_m?: number };
    client_id?: string; // idempotency key: resending the same one never creates a duplicate
    captured_at?: string; // ISO time the officer pressed Submit (differs from receipt time when queued offline)
    test_points?: { reference: number; indicated: number }[];
    checks?: Record<string, boolean>;
    seal_number?: string;
  }) =>
    api.post<Inspection>("/inspections", body),
  get: (id: string) => api.get<Inspection>(`/inspections/${id}`),
  formSpec: (type: string) => api.get<InspectionFormSpec>(`/inspections/form-spec?type=${encodeURIComponent(type)}`),
  forApplication: (applicationId: string) => api.get<Inspection>(`/inspections/by-application/${applicationId}`),
};

// ---- Dashboards ----
export const DashboardApi = {
  owner: () => api.get<OwnerDashboard>("/dashboard/owner"),
  lmo: () => api.get<OfficerDashboard>("/dashboard/lmo"),
  gatc: () => api.get<OfficerDashboard>("/dashboard/gatc"),
  admin: () => api.get<AdminDashboard>("/dashboard/admin"),
};

// ---- Certificates ----
export const CertificateApi = {
  verifyPublic: (certId: string) =>
    api.get<CertificateVerifyResponse>(`/certificates/verify/${encodeURIComponent(certId)}`, { public: true }),
  get: (certId: string) => api.get<Certificate>(`/certificates/${certId}`),
  list: (params?: CertificateFilters) => api.get<Certificate[]>(`/certificates/${toQuery(params)}`),
  pending: () => api.get<PendingCertificate[]>("/certificates/pending"),
  generate: (applicationId: string) => api.post<Certificate>(`/certificates/generate/${applicationId}`),
  pdf: (certId: string) => fetchBlob(`/certificates/${certId}/pdf`),
};

// ---- Uploads ----
export const UploadApi = {
  photo: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post<{ url: string }>("/uploads/photo", form, { isForm: true });
  },
};

// ---- Reports (CSV / PDF downloads) ----
// Same filters as the lists, so a file holds exactly what the screen shows.
export type ReportKind = "applications" | "certificates" | "instruments" | "audit-logs";
export type ReportFormat = "csv" | "pdf";

export const ReportsApi = {
  download: (kind: ReportKind, format: ReportFormat, params?: object) =>
    downloadFile(`/reports/${kind}${toQuery({ ...params, format })}`),
};
