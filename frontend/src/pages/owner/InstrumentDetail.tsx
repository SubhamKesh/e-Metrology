import { Link, useNavigate, useParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Card";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { ApplicationStatusBadge } from "@/components/ui/StatusBadge";
import { useApplications, useInstrument } from "@/hooks/useData";
import { ApiError } from "@/lib/api";

export default function InstrumentDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data: instrument, isLoading, isError, error, refetch } = useInstrument(id);
  const { data: applications } = useApplications();
  const related = applications?.filter((a) => a.instrument_id === id) ?? [];

  if (isLoading) {
    return (
      <div className="max-w-2xl space-y-3">
        <Skeleton className="h-8 w-1/2" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (isError || !instrument) {
    return <ErrorState message={error instanceof ApiError ? error.message : "Instrument not found."} onRetry={refetch} />;
  }

  return (
    <div className="max-w-2xl">
      <PageHeader
        title={instrument.type}
        description={`${instrument.manufacturer} · ${instrument.model}`}
        action={
          <Button onClick={() => navigate(`/app/owner/applications/new?instrument=${instrument.id}`)}>
            Apply for verification
          </Button>
        }
      />

      <Panel className="p-5">
        <dl className="grid grid-cols-2 gap-y-4 text-sm">
          <Field label="UIID" value={instrument.uiid ?? instrument.serial_no} mono />
          <Field label="Capacity" value={instrument.capacity} />
          <Field label="Location" value={instrument.location} />
          <Field label="Instrument ID" value={instrument.id} mono />
        </dl>
      </Panel>

      <h2 className="mb-3 mt-8 font-display text-lg text-ink">Verification history</h2>
      {related.length === 0 ? (
        <p className="text-sm text-slate-400">No applications submitted for this instrument yet.</p>
      ) : (
        <div className="divide-y divide-line rounded-lg border border-line bg-white">
          {related.map((a) => (
            <Link
              key={a.id}
              to={`/app/owner/applications/${a.id}`}
              className="flex items-center justify-between px-4 py-3 hover:bg-paper2/60"
            >
              <span className="font-mono text-xs text-slate-500">{a.id}</span>
              <ApplicationStatusBadge status={a.status} />
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className={`mt-0.5 text-ink ${mono ? "font-mono text-xs" : ""}`}>{value}</dd>
    </div>
  );
}
