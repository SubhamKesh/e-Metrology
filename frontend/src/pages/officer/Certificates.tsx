import { useParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/AppShell";
import { CertificatesTable } from "@/components/domain/CertificatesTable";
import { CertificateDetailCore } from "@/components/domain/CertificateDetailCore";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { CertificatesFilterBar, EMPTY_CERTIFICATE_FILTERS } from "@/components/domain/CertificatesFilterBar";
import { useFilters } from "@/hooks/useFilters";
import { useCertificate, useCertificates } from "@/hooks/useData";
import { ApiError } from "@/lib/api";
import type { Role } from "@/lib/types";

export function OfficerCertificates({ role }: { role: Extract<Role, "lmo" | "gatc"> }) {
  const filters = useFilters(EMPTY_CERTIFICATE_FILTERS);
  const { data, isLoading, isError, error, refetch } = useCertificates(filters.query);
  return (
    <div>
      <PageHeader title="Certificates" description="Certificates issued from applications assigned to you." />
      <CertificatesFilterBar filters={filters} />
      <CertificatesTable
        emptyTitle={filters.active ? "No certificates match" : undefined}
        emptyDescription={filters.active ? "Try a different search or clear the filters." : undefined}
        certificates={data}
        isLoading={isLoading}
        isError={isError}
        error={error}
        onRetry={refetch}
        basePath={`/app/${role}/certificates`}
      />
    </div>
  );
}

export function OfficerCertificateDetail() {
  const { id } = useParams();
  const { data, isLoading, isError, error, refetch } = useCertificate(id);
  if (isLoading) return <Skeleton className="h-64 w-full max-w-2xl" />;
  if (isError || !data) {
    return <ErrorState message={error instanceof ApiError ? error.message : "Certificate not found."} onRetry={refetch} />;
  }
  return <CertificateDetailCore certificate={data} />;
}
