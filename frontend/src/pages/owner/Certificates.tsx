import { useParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/AppShell";
import { CertificatesTable } from "@/components/domain/CertificatesTable";
import { CertificateDetailCore } from "@/components/domain/CertificateDetailCore";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { Button, ButtonLink } from "@/components/ui/Button";
import { useApplications, useCertificate, useCertificates, useGenerateCertificate, usePendingCertificates } from "@/hooks/useData";
import { ApiError } from "@/lib/api";

// Certified applications with no certificate yet: generation is still running, or it
// failed. Either way the owner sees why the list is short and can retry in one click.
function PendingCertificates() {
  const { data: pending } = usePendingCertificates();
  const generate = useGenerateCertificate();
  if (!pending || pending.length === 0) return null;
  return (
    <div className="mb-4 space-y-2" role="status">
      {pending.map((p) => (
        <div
          key={p.application_id}
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-paper2/60 px-4 py-3 text-sm"
        >
          <div>
            <p className="text-ink">
              {p.instrument?.type ?? "Instrument"}
              {p.instrument?.uiid ? <span className="ml-2 font-mono text-xs text-slate-500">{p.instrument.uiid}</span> : null}
            </p>
            <p className="text-slate-500">
              {p.failed
                ? "Your inspection passed, but the certificate couldn't be generated yet. We're retrying automatically."
                : "Your inspection passed. The certificate is being prepared and will appear here shortly."}
            </p>
          </div>
          <Button
            size="sm"
            variant="secondary"
            loading={generate.isPending && generate.variables === p.application_id}
            onClick={() => generate.mutate(p.application_id)}
          >
            Generate now
          </Button>
        </div>
      ))}
      {generate.isError && (
        <p className="text-sm text-danger">
          {generate.error instanceof ApiError ? generate.error.message : "Couldn't generate the certificate. Please try again."}
        </p>
      )}
    </div>
  );
}

export function OwnerCertificates() {
  const { data, isLoading, isError, error, refetch } = useCertificates();
  return (
    <div>
      <PageHeader title="Certificates" description="All certificates issued for your instruments." />
      <PendingCertificates />
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
  const { data: allCertificates } = useCertificates();
  const { data: applications } = useApplications();
  if (isLoading) return <Skeleton className="h-64 w-full max-w-2xl" />;
  if (isError || !data) {
    return <ErrorState message={error instanceof ApiError ? error.message : "Certificate not found."} onRetry={refetch} />;
  }
  // Renew only the newest certificate of an instrument, only after it has expired, and not while an application is already running.
  const isLatest =
    !data.instrument_id ||
    !(allCertificates ?? []).some(
      (c) => c.instrument_id === data.instrument_id && new Date(c.valid_until) > new Date(data.valid_until),
    );
  const inProgress = (applications ?? []).some(
    (a) => a.instrument_id === data.instrument_id && ["submitted", "scheduled", "inspected"].includes(a.status),
  );
  const renew =
    data.instrument_id && isLatest ? (
      !data.is_expired ? (
        <Button size="sm" disabled title="Re-verification opens once this certificate has expired">
          Renewable after {new Date(data.valid_until).toLocaleDateString("en-IN", { dateStyle: "medium" })}
        </Button>
      ) : inProgress ? (
        <Button size="sm" disabled>
          Renewal in progress
        </Button>
      ) : (
        <ButtonLink
          size="sm"
          to={`/app/owner/applications/new?instrument=${data.instrument_id}&renew=${data.id}&cert_no=${encodeURIComponent(data.cert_no ?? "")}`}
        >
          Renew certificate
        </ButtonLink>
      )
    ) : undefined;
  return <CertificateDetailCore certificate={data} extraActions={renew} />;
}
