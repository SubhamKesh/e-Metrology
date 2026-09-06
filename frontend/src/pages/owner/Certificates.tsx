import { useParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/AppShell";
import { CertificatesTable } from "@/components/domain/CertificatesTable";
import { CertificateDetailCore } from "@/components/domain/CertificateDetailCore";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { useCertificate, useCertificates } from "@/hooks/useData";
import { ApiError } from "@/lib/api";

export function OwnerCertificates() {
  const { data, isLoading, isError, error, refetch } = useCertificates();
  return (
    <div>
      <PageHeader title="Certificates" description="All certificates issued for your instruments." />
      <CertificatesTable
        certificates={data}
        isLoading={isLoading}
        isError={isError}
        error={error}
        onRetry={refetch}
        basePath="/app/owner/certificates"
      />
    </div>
  );
}

export function OwnerCertificateDetail() {
  const { id } = useParams();
  const { data, isLoading, isError, error, refetch } = useCertificate(id);
  if (isLoading) return <Skeleton className="h-64 w-full max-w-2xl" />;
  if (isError || !data) {
    return <ErrorState message={error instanceof ApiError ? error.message : "Certificate not found."} onRetry={refetch} />;
  }
  return <CertificateDetailCore certificate={data} />;
}
