import { api } from "./api";
import type {
  AdminDashboard,
  Application,
  Certificate,
  CertificateVerifyResponse,
  Inspection,
  Instrument,
  OfficerDashboard,
  OwnerDashboard,
  Role,
  User,
} from "./types";

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
}

export const AuthApi = {
  register: (body: RegisterPayload) => api.post<AuthResponse>("/auth/register", body, { public: true }),
  login: (body: { email: string; password: string }) =>
    api.post<AuthResponse>("/auth/login", body, { public: true }),
  me: () => api.get<{ user: User }>("/auth/me"),
  logout: () => api.post<void>("/auth/logout"),
  changePassword: (body: { current_password: string; new_password: string }) =>
    api.post<User>("/auth/change-password", body),
};

// ---- Admin: officer accounts (invite-only lmo/gatc) ----
export interface CreateOfficerPayload {
  name: string;
  email: string;
  role: "lmo" | "gatc";
  org_name?: string;
  contact?: string;
}
export interface CreateOfficerResponse {
  user: User;
  temp_password: string;
  emailed: boolean;
}

export const AdminUsersApi = {
  listOfficers: () => api.get<User[]>("/admin/users"),
  listPending: () => api.get<User[]>("/admin/users/pending"),
  createOfficer: (body: CreateOfficerPayload) =>
    api.post<CreateOfficerResponse>("/admin/users/create-officer", body),
  approve: (id: string) => api.post<User>(`/admin/users/${id}/approve`),
  reject: (id: string) => api.post<User>(`/admin/users/${id}/reject`),
};

// ---- Instruments ----
export const InstrumentApi = {
  create: (body: Omit<Instrument, "id" | "owner_id" | "uiid">) => api.post<Instrument>("/instruments", body),
  list: (params?: { owner_id?: string }) => {
    const qs = params?.owner_id ? `?owner_id=${encodeURIComponent(params.owner_id)}` : "";
    return api.get<Instrument[]>(`/instruments${qs}`);
  },
  get: (id: string) => api.get<Instrument>(`/instruments/${id}`),
};

// ---- Applications ----
export const ApplicationApi = {
  create: (body: { instrument_id: string }) => api.post<Application>("/applications", body),
  list: (params?: { mine?: boolean; status?: string }) => {
    const usp = new URLSearchParams();
    if (params?.mine) usp.set("mine", "true");
    if (params?.status) usp.set("status", params.status);
    const qs = usp.toString();
    return api.get<Application[]>(`/applications${qs ? `?${qs}` : ""}`);
  },
  get: (id: string) => api.get<Application>(`/applications/${id}`),
  claim: (id: string) => api.post<Application>(`/applications/${id}/claim`),
};

// ---- Inspections ----
export const InspectionApi = {
  create: (body: { application_id: string; observations: string; result: "pass" | "fail"; photos: string[] }) =>
    api.post<Inspection>("/inspections", body),
  get: (id: string) => api.get<Inspection>(`/inspections/${id}`),
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
  list: () => api.get<Certificate[]>("/certificates/"),
};

// ---- Uploads ----
export const UploadApi = {
  photo: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post<{ url: string }>("/uploads/photo", form, { isForm: true });
  },
};
