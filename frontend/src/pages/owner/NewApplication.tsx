import { type FormEvent, useCallback, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/AppShell";
import { SelectInput } from "@/components/ui/Field";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Card";
import { useCreateApplication, useInstruments } from "@/hooks/useData";
import { ApiError } from "@/lib/api";
import { EmptyState } from "@/components/ui/States";
import { SupportingDocuments } from "@/components/domain/SupportingDocuments";

export default function NewApplication() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { data: instruments, isLoading } = useInstruments();
  const create = useCreateApplication();
  const [instrumentId, setInstrumentId] = useState(params.get("instrument") ?? "");
  // Set by the Renew button on a certificate; the server links the newest certificate otherwise.
  const renewCertId = params.get("renew") ?? undefined;
  const renewCertNo = params.get("cert_no");
  const [error, setError] = useState<string | null>(null);
  // Whether every required document for this instrument is uploaded; Submit stays off until then.
  const [docs, setDocs] = useState({ complete: false, loading: true });
  const onDocsStatus = useCallback((status: { complete: boolean; loading: boolean }) => setDocs(status), []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const app = await create.mutateAsync({
        instrument_id: instrumentId,
        // Only meaningful while the instrument still matches the one being renewed.
        previous_certificate_id: renewCertId && instrumentId === params.get("instrument") ? renewCertId : undefined,
      });
      navigate(`/app/owner/applications/${app.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    }
  }

  if (!isLoading && (instruments ?? []).length === 0) {
    return (
      <div className="max-w-xl">
        <PageHeader title="Apply for verification" />
        <EmptyState
          title="Register an instrument first"
          description="You need at least one registered instrument before you can submit a verification application."
          action={
            <ButtonLink to="/app/owner/instruments/new">Register instrument</ButtonLink>
          }
        />
      </div>
    );
  }

  return (
    <div className="max-w-xl">
      <PageHeader title="Apply for verification" description="Submit a verification or re-verification request for one of your instruments." />
      <Panel className="p-6">
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <SelectInput
            label="Instrument"
            required
            placeholder="Select an instrument"
            value={instrumentId}
            onChange={(e) => setInstrumentId(e.target.value)}
            options={(instruments ?? []).map((i) => ({
              value: i.id,
              label: `${i.type} · ${i.uiid}`,
            }))}
          />
          {renewCertId && renewCertNo && instrumentId === params.get("instrument") && (
            <p className="text-sm text-slate-600">
              Re-verification of certificate <span className="font-mono text-xs">{renewCertNo}</span>.
            </p>
          )}
          {instrumentId && <SupportingDocuments key={instrumentId} instrumentId={instrumentId} onStatus={onDocsStatus} bare />}
          {instrumentId && !docs.loading && !docs.complete && (
            <p className="text-sm text-slate-600">Upload every document marked * to enable Submit.</p>
          )}
          {error && <p className="text-sm text-danger">{error}</p>}
          <div className="mt-2 flex flex-col-reverse gap-3 sm:flex-row">
            <Button type="submit" loading={create.isPending} disabled={!instrumentId || docs.loading || !docs.complete}>
              Submit application
            </Button>
            <Button type="button" variant="secondary" onClick={() => navigate(-1)}>
              Cancel
            </Button>
          </div>
        </form>
      </Panel>
    </div>
  );
}
