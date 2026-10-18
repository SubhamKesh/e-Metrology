import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  type ApplicationFilters,
  type CertificateFilters,
  type InstrumentFilters,
  ApplicationApi,
  CertificateApi,
  DashboardApi,
  GeoApi,
  InspectionApi,
  InstrumentApi,
  UploadApi,
} from "@/lib/endpoints";
import type { InspectionFormSpec } from "@/lib/types";
import type { AdminDashboard, OfficerDashboard, OwnerDashboard, Role, ScheduleInput } from "@/lib/types";

// ---- Dashboards ----
export function useDashboard(role: Role) {
  return useQuery<OwnerDashboard | OfficerDashboard | AdminDashboard>({
    queryKey: ["dashboard", role],
    queryFn: () => {
      switch (role) {
        case "owner":
          return DashboardApi.owner();
        case "lmo":
          return DashboardApi.lmo();
        case "gatc":
          return DashboardApi.gatc();
        case "admin":
          return DashboardApi.admin();
      }
    },
  });
}

// ---- Instruments ----
export function useInstruments(params?: InstrumentFilters) {
  return useQuery({
    queryKey: ["instruments", params],
    placeholderData: keepPreviousData, // keep the rows on screen while a search is typed
    queryFn: async () => {
      try {
        return await InstrumentApi.list(params);
      } catch (err) {
        // lmo/gatc users are not authorized to list all instruments (403).
        // In those views we don't need the full instrument list, so treat
        // 403 as an empty result to avoid noisy errors in the officer UI.
        // Re-throw other errors to surface real failures.
        if (
          err instanceof Error &&
          "status" in err &&
          typeof (err as { status?: number }).status === "number" &&
          (err as { status?: number }).status === 403
        ) {
          return [];
        }
        throw err;
      }
    },
  });
}

export function useInstrument(id?: string) {
  return useQuery({
    queryKey: ["instrument", id],
    queryFn: () => InstrumentApi.get(id as string),
    enabled: !!id,
  });
}

export function useCreateInstrument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: InstrumentApi.create,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instruments"] }),
  });
}

// Static reference data — types rarely change, so a long staleTime avoids
// re-fetching on every form mount.
export function useInstrumentTypeSpecs() {
  return useQuery({
    queryKey: ["instrument-type-specs"],
    queryFn: InstrumentApi.typeSpecs,
    staleTime: 60 * 60 * 1000,
  });
}

// ---- Geography (states/districts) ----
export function useGeoStates() {
  return useQuery({
    queryKey: ["geo-states"],
    queryFn: GeoApi.states,
    staleTime: 60 * 60 * 1000,
  });
}

export function useGeoDistricts(stateCode?: string) {
  return useQuery({
    queryKey: ["geo-districts", stateCode],
    queryFn: () => GeoApi.districts(stateCode as string),
    enabled: !!stateCode,
    staleTime: 60 * 60 * 1000,
  });
}

// ---- Applications ----
export function useApplications(params?: ApplicationFilters & { mine?: boolean; pollInterval?: number }) {
  const { pollInterval, ...filters } = params ?? {};
  return useQuery({
    queryKey: ["applications", filters],
    queryFn: () => ApplicationApi.list(filters),
    placeholderData: keepPreviousData, // keep the rows on screen while a search is typed
    // Optional polling for views that want near-real-time updates (officer queue)
    refetchInterval: pollInterval ?? false,
  });
}

export function useApplication(id?: string) {
  return useQuery({
    queryKey: ["application", id],
    queryFn: () => ApplicationApi.get(id as string),
    enabled: !!id,
  });
}

export function useCreateApplication() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ApplicationApi.create,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["applications"] }),
  });
}

function refreshApplication(qc: ReturnType<typeof useQueryClient>, id: string) {
  qc.invalidateQueries({ queryKey: ["applications"] });
  qc.invalidateQueries({ queryKey: ["application", id] });
  // A booking changes the places left in a slot.
  qc.invalidateQueries({ queryKey: ["slots"] });
}

export function useClaimApplication() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string } & ScheduleInput) => ApplicationApi.claim(id, body),
    onSuccess: (_data, vars) => refreshApplication(qc, vars.id),
  });
}

export function useRescheduleApplication() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string } & ScheduleInput) => ApplicationApi.schedule(id, body),
    onSuccess: (_data, vars) => refreshApplication(qc, vars.id),
  });
}

export function useAssignApplication() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; officer_id: string } & ScheduleInput) =>
      ApplicationApi.assign(id, body),
    onSuccess: (_data, vars) => refreshApplication(qc, vars.id),
  });
}

// Places left per date and slot for one officer (admins pass the officer, officers omit it).
export function useSlotAvailability(officerId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ["slots", officerId ?? "me"],
    queryFn: () => ApplicationApi.slots({ officer_id: officerId, days: 30 }),
    enabled,
    staleTime: 10_000,
  });
}

// ---- Inspections ----
export function useSubmitInspection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: InspectionApi.create,
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["applications"] });
      qc.invalidateQueries({ queryKey: ["application", vars.application_id] });
      qc.invalidateQueries({ queryKey: ["inspection-of", vars.application_id] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

// What to record for this instrument type. Remembered on the device (the last copy is shown at once and
// refreshed in the background), so the form still opens if the signal drops after the officer first loaded it.
const specKey = (type: string) => `maapsetu:form-spec:${type}`;
function readSavedSpec(type?: string): InspectionFormSpec | undefined {
  if (!type) return undefined;
  try {
    const raw = localStorage.getItem(specKey(type));
    return raw ? (JSON.parse(raw) as InspectionFormSpec) : undefined;
  } catch {
    return undefined;
  }
}
export function useInspectionFormSpec(type?: string) {
  return useQuery({
    queryKey: ["inspection-form-spec", type],
    enabled: !!type,
    queryFn: async () => {
      const spec = await InspectionApi.formSpec(type!);
      try {
        localStorage.setItem(specKey(type!), JSON.stringify(spec));
      } catch {
        // storage full or blocked: the form still works while online
      }
      return spec;
    },
    initialData: () => readSavedSpec(type),
    initialDataUpdatedAt: 0,
    staleTime: 60 * 60 * 1000,
  });
}

// The recorded inspection of an application (officer, admin, or the instrument's owner).
export function useApplicationInspection(applicationId?: string, enabled = true) {
  return useQuery({
    queryKey: ["inspection-of", applicationId],
    queryFn: () => InspectionApi.forApplication(applicationId!),
    enabled: !!applicationId && enabled,
    retry: false,
  });
}

export function useUploadPhoto() {
  return useMutation({ mutationFn: UploadApi.photo });
}

// ---- Certificates ----
export function useCertificates(params?: CertificateFilters) {
  return useQuery({
    queryKey: ["certificates", params ?? {}],
    queryFn: () => CertificateApi.list(params),
    placeholderData: keepPreviousData,
  });
}

// Certified applications whose certificate isn't generated yet. Polls while any
// exist so the certificate appears on its own once the server finishes.
export function usePendingCertificates() {
  const qc = useQueryClient();
  return useQuery({
    queryKey: ["certificates-pending"],
    queryFn: async () => {
      const pending = await CertificateApi.pending();
      // Something just finished generating -> refresh the real list.
      qc.invalidateQueries({ queryKey: ["certificates"] });
      return pending;
    },
    refetchInterval: (query) => (query.state.data && query.state.data.length > 0 ? 8000 : false),
  });
}

export function useGenerateCertificate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (applicationId: string) => CertificateApi.generate(applicationId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["certificates"] });
      qc.invalidateQueries({ queryKey: ["certificates-pending"] });
    },
  });
}

export function useCertificate(id?: string) {
  return useQuery({
    queryKey: ["certificate", id],
    queryFn: () => CertificateApi.get(id as string),
    enabled: !!id,
  });
}

export function useVerifyCertificate(certId?: string) {
  return useQuery({
    queryKey: ["certificate-verify", certId],
    queryFn: () => CertificateApi.verifyPublic(certId as string),
    enabled: !!certId,
    retry: false,
  });
}
