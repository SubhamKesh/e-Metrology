import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/AppShell";
import { SelectInput } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Card";
import { useCreateApplication, useInstruments } from "@/hooks/useData";
import { ApiError } from "@/lib/api";
import { EmptyState } from "@/components/ui/States";
import { Link } from "react-router-dom";

export default function NewApplication() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { data: instruments, isLoading } = useInstruments();
  const create = useCreateApplication();
  const [instrumentId, setInstrumentId] = useState(params.get("instrument") ?? "");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const app = await create.mutateAsync({ instrument_id: instrumentId });
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
            <Link to="/app/owner/instruments/new">
              <Button>Register instrument</Button>
            </Link>
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
              label: `${i.type} · ${i.serial_no}`,
            }))}
          />
          {error && <p className="text-sm text-danger">{error}</p>}
          <div className="mt-2 flex gap-3">
            <Button type="submit" loading={create.isPending} disabled={!instrumentId}>
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
