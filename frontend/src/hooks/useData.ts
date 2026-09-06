import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApplicationApi,
  CertificateApi,
  DashboardApi,
  InspectionApi,
  InstrumentApi,
  UploadApi,
} from "@/lib/endpoints";
import type { Role } from "@/lib/types";

// ---- Dashboards ----
export function useDashboard(role: Role) {
  return useQuery({
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
    queryFn: () => InstrumentApi.list(params),
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
export function useApplications(params?: { mine?: boolean; status?: string }) {
  return useQuery({
    queryKey: ["applications", params],
    queryFn: () => ApplicationApi.list(params),
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
