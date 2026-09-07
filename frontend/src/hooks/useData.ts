import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApplicationApi,
  CertificateApi,
  DashboardApi,
  InspectionApi,
  InstrumentApi,
  UploadApi,
} from "@/lib/endpoints";
import type { AdminDashboard, OfficerDashboard, OwnerDashboard, Role } from "@/lib/types";

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
export function useInstruments(params?: { owner_id?: string }) {
  return useQuery({
    queryKey: ["instruments", params],
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

// ---- Applications ----
export function useApplications(params?: { mine?: boolean; status?: string; pollInterval?: number }) {
  return useQuery({
    queryKey: ["applications", { mine: params?.mine, status: params?.status }],
    queryFn: () => ApplicationApi.list(params),
    // Optional polling for views that want near-real-time updates (officer queue)
    refetchInterval: params?.pollInterval ?? false,
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

export function useClaimApplication() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => ApplicationApi.claim(id),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ["applications"] });
      qc.invalidateQueries({ queryKey: ["application", id] });
    },
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
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useUploadPhoto() {
  return useMutation({ mutationFn: UploadApi.photo });
}

// ---- Certificates ----
export function useCertificates() {
  return useQuery({ queryKey: ["certificates"], queryFn: CertificateApi.list });
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
