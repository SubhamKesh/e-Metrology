import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/AppShell";
import { Panel } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { TextArea } from "@/components/ui/Field";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { PhotoUploader } from "@/components/domain/PhotoUploader";
import { useApplication, useInstrument, useSubmitInspection } from "@/hooks/useData";
import { ApiError } from "@/lib/api";
import type { InspectionResult, Role } from "@/lib/types";
import { cn } from "@/lib/cn";

export function InspectionWorkflow({ role }: { role: Extract<Role, "lmo" | "gatc"> }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data: application, isLoading, isError, error, refetch } = useApplication(id);
  const { data: instrument } = useInstrument(application?.instrument_id);
  const submit = useSubmitInspection();

  const [serialConfirmed, setSerialConfirmed] = useState(false);
  const [enteredSerial, setEnteredSerial] = useState("");
  const [photos, setPhotos] = useState<string[]>([]);
  const [observations, setObservations] = useState("");
  const [result, setResult] = useState<InspectionResult | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  if (isLoading) return <Skeleton className="h-64 w-full max-w-2xl" />;
  if (isError || !application) {
    return <ErrorState message={error instanceof ApiError ? error.message : "Application not found."} onRetry={refetch} />;
  }

  if (application.status !== "scheduled") {
    return (
      <ErrorState
        message={`This application is currently "${application.status}" — verification can only be submitted while it's scheduled.`}
        onRetry={() => navigate(`/app/${role}/applications/${id}`)}
      />
    );
  }

  const serialMatches = instrument ? enteredSerial.trim() === instrument.uiid : false;
  const identityBlocked = enteredSerial.length > 0 && !serialMatches;

  async function onSubmit(finalResult: InspectionResult) {
    if (!id) return;
    setSubmitError(null);
    try {
      await submit.mutateAsync({ application_id: id, observations, result: finalResult, photos });
      navigate(`/app/${role}/applications/${id}`);
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : "Couldn't submit this inspection. Try again.");
    }
  }

  const canSubmit = serialConfirmed && serialMatches && observations.trim().length > 0;

  return (
    <div className="max-w-2xl">
      <PageHeader title="Field verification" description={instrument ? `${instrument.type} · ${instrument.manufacturer} ${instrument.model}` : undefined} />

      {/* Step 1: Physical identity check */}
      <Panel className="mb-5 p-5">
        <h2 className="mb-3 text-sm font-medium text-ink">1. Confirm instrument identity</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="rounded-md border border-line bg-paper2/40 p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">Registered</p>
            <p className="mt-1 font-mono text-sm text-ink">{instrument?.uiid ?? "—"}</p>
          </div>
          <div>
            <label htmlFor="entered-serial" className="text-sm font-medium text-ink">
              UIID on the instrument's sticker/QR
            </label>
            <input
              id="entered-serial"
              value={enteredSerial}
              onChange={(e) => setEnteredSerial(e.target.value)}
              placeholder="Enter what you see on the plate"
              className="mt-1.5 h-10 w-full rounded-md border border-line px-3 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-teal/30"
            />
          </div>
        </div>
        {enteredSerial.length > 0 && (
          <div
            className={cn(
              "mt-4 rounded-md px-4 py-2.5 text-sm font-medium",
              serialMatches ? "bg-success-50 text-success" : "bg-danger-50 text-danger",
            )}
          >
            {serialMatches ? "✓ Identity matched" : "✕ Identity mismatch — do not proceed"}
          </div>
        )}
        {serialMatches && (
          <label className="mt-4 flex items-center gap-2 text-sm text-ink">
            <input type="checkbox" checked={serialConfirmed} onChange={(e) => setSerialConfirmed(e.target.checked)} />
            I've physically confirmed this is the registered instrument.
          </label>
        )}
      </Panel>

      {/* Remaining steps only unlock once identity is confirmed, so a mismatch can't be worked around */}
      <fieldset disabled={identityBlocked || !serialConfirmed} className="disabled:pointer-events-none disabled:opacity-40">
        <Panel className="mb-5 p-5">
          <h2 className="mb-3 text-sm font-medium text-ink">2. Evidence photographs</h2>
          <PhotoUploader photos={photos} onChange={setPhotos} />
        </Panel>

        <Panel className="mb-5 p-5">
          <h2 className="mb-3 text-sm font-medium text-ink">3. Observations</h2>
          <TextArea
            label="Inspection notes"
            placeholder="Describe what was checked and what was found."
            value={observations}
            onChange={(e) => setObservations(e.target.value)}
            required
          />
        </Panel>

        <Panel className="p-5">
          <h2 className="mb-3 text-sm font-medium text-ink">4. Result</h2>
          <div className="flex flex-col gap-3 sm:flex-row">
            <Button
              type="button"
              className="flex-1"
              loading={submit.isPending && result === "pass"}
              disabled={!canSubmit || submit.isPending}
              onClick={() => {
                setResult("pass");
                onSubmit("pass");
              }}
            >
              Submit — Pass
            </Button>
            <Button
              type="button"
              variant="danger"
              className="flex-1"
              loading={submit.isPending && result === "fail"}
              disabled={!canSubmit || submit.isPending}
              onClick={() => {
                setResult("fail");
                onSubmit("fail");
              }}
            >
              Submit — Fail
            </Button>
          </div>
          {!canSubmit && (
            <p className="mt-3 text-sm text-slate-400">
              Confirm identity and add observations before submitting.
            </p>
          )}
          {submitError && <p className="mt-3 text-sm text-danger">{submitError}</p>}
        </Panel>
      </fieldset>
    </div>
  );
}
