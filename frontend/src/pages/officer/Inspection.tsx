import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/AppShell";
import { Panel } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { TextArea } from "@/components/ui/Field";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { PhotoUploader } from "@/components/domain/PhotoUploader";
import { QrScanner } from "@/components/domain/QrScanner";
import { getGpsFix, type GpsFix } from "@/lib/geo";
import { useApplication, useInstrument, useSubmitInspection } from "@/hooks/useData";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useQueuedInspections } from "@/hooks/useOfflineSync";
import { enqueueInspection } from "@/lib/offlineQueue";
import type { IdentityMethod, InspectionResult, Role } from "@/lib/types";
import { cn } from "@/lib/cn";

export function InspectionWorkflow({ role }: { role: Extract<Role, "lmo" | "gatc"> }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data: application, isLoading, isError, error, refetch } = useApplication(id);
  const { data: instrument } = useInstrument(application?.instrument_id);
  const submit = useSubmitInspection();
  const { user } = useAuth();
  const queued = useQueuedInspections(user?.id);
  // One id per inspection attempt: a retry (or a later sync of a queued copy) can never create a duplicate.
  const clientId = useRef<string>(crypto.randomUUID());
  const [pendingPhotos, setPendingPhotos] = useState<File[]>([]);
  const [savedOffline, setSavedOffline] = useState(false);

  const [serialConfirmed, setSerialConfirmed] = useState(false);
  const [enteredSerial, setEnteredSerial] = useState("");
  const [photos, setPhotos] = useState<string[]>([]);
  const [observations, setObservations] = useState("");
  const [result, setResult] = useState<InspectionResult | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [identityMethod, setIdentityMethod] = useState<IdentityMethod>("manual");
  const [gps, setGps] = useState<GpsFix | null>(null);
  const [locating, setLocating] = useState(false);

  const captureGps = useCallback(async () => {
    setLocating(true);
    const fix = await getGpsFix(12000);
    setGps(fix);
    setLocating(false);
    return fix;
  }, []);

  // GPS is mandatory: start locating as soon as the page opens so a fix is ready by submit time.
  useEffect(() => {
    captureGps();
  }, [captureGps]);

  const handleScan = useCallback((uiid: string) => {
    setEnteredSerial(uiid);
    setIdentityMethod("qr");
    setScanning(false);
  }, []);

  if (isLoading) return <Skeleton className="h-64 w-full max-w-2xl" />;
  if (!application) {
    return <ErrorState message={error instanceof ApiError ? error.message : "Application not found."} onRetry={refetch} />;
  }

  const alreadyQueued = savedOffline || queued.some((q) => q.application_id === id && q.status === "pending");
  if (alreadyQueued) {
    return (
      <div className="max-w-2xl">
        <PageHeader title="Saved on this device" />
        <Panel className="p-5">
          <p className="text-sm text-ink">
            This inspection is saved on your device and will be sent automatically as soon as you're back online. You don't need
            to submit it again. Keep this device signed in to MaapSetu until it has been sent.
          </p>
          <Button type="button" className="mt-4" onClick={() => navigate(`/app/${role}`)}>
            Back to dashboard
          </Button>
        </Panel>
      </div>
    );
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
      // Location is mandatory: take a fresh fix, fall back to the one already captured.
      const fix = (await getGpsFix(8000)) ?? gps;
      if (!fix) {
        setGps(null);
        setSubmitError("Location is required to submit. Turn on location services for this site, then try again.");
        return;
      }
      const capturedAt = new Date().toISOString();

      async function saveOnDevice() {
        if (!user) throw new Error("not signed in");
        await enqueueInspection({
          client_id: clientId.current,
          user_id: user.id,
          application_id: id!,
          label: instrument ? `${instrument.type} · ${instrument.manufacturer} ${instrument.model}` : `Application ${id}`,
          observations,
          result: finalResult,
          photos,
          pending_photos: pendingPhotos.map((f) => ({ name: f.name, type: f.type, blob: f })),
          identity_method: identityMethod,
          location: fix!,
          captured_at: capturedAt,
        });
        setSavedOffline(true);
      }

      // Offline already (or photos still waiting to upload): keep it on the device and send it later.
      if (!navigator.onLine || pendingPhotos.length > 0) {
        await saveOnDevice();
        return;
      }
      try {
        await submit.mutateAsync({
          application_id: id,
          observations,
          result: finalResult,
          photos,
          identity_method: identityMethod,
          location: fix,
          client_id: clientId.current,
          captured_at: capturedAt,
        });
      } catch (err) {
        // Connection dropped mid-submit. The server may or may not have received it; the
        // client_id makes the later sync safe either way.
        if (err instanceof ApiError && err.status === 0) {
          await saveOnDevice();
          return;
        }
        throw err;
      }
      navigate(`/app/${role}/applications/${id}`);
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : "Couldn't submit this inspection. Try again.");
    }
  }

  const canSubmit = serialConfirmed && serialMatches && observations.trim().length > 0 && !!gps;

  return (
    <div className="max-w-2xl">
      <PageHeader title="Field verification" description={instrument ? `${instrument.type} · ${instrument.manufacturer} ${instrument.model}` : undefined} />

      {/* Step 1: Physical identity check */}
      <Panel className="mb-5 p-5">
        <h2 className="mb-3 text-sm font-medium text-ink">1. Confirm instrument identity</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="rounded-md border border-line bg-paper2/40 p-4">
            <p className="text-xs uppercase tracking-wide text-slate-500">Registered</p>
            <p className="mt-1 font-mono text-sm text-ink">{instrument?.uiid ?? "—"}</p>
          </div>
          <div>
            <label htmlFor="entered-serial" className="text-sm font-medium text-ink">
              UIID on the instrument's sticker/QR
            </label>
            <input
              id="entered-serial"
              value={enteredSerial}
              onChange={(e) => {
                setEnteredSerial(e.target.value);
                setIdentityMethod("manual");
              }}
              placeholder="Enter what you see on the plate"
              className="mt-1.5 h-10 w-full rounded-md border border-line px-3 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-teal/30"
            />
            <Button type="button" variant="secondary" size="sm" className="mt-2" onClick={() => setScanning((v) => !v)}>
              {scanning ? "Hide scanner" : "Scan QR with camera"}
            </Button>
          </div>
        </div>
        {scanning && <QrScanner onScan={handleScan} onClose={() => setScanning(false)} />}
        {enteredSerial.length > 0 && (
          <div
            className={cn(
              "mt-4 rounded-md px-4 py-2.5 text-sm font-medium",
              serialMatches ? "bg-success-50 text-success" : "bg-danger-50 text-danger",
            )}
          >
            {serialMatches
              ? `✓ Identity matched${identityMethod === "qr" ? " (scanned)" : ""}`
              : "✕ Identity mismatch — do not proceed"}
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
          <PhotoUploader photos={photos} onChange={setPhotos} pending={pendingPhotos} onPendingChange={setPendingPhotos} />
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
          <div className="mb-4 flex items-center justify-between gap-3 rounded-md border border-line px-4 py-2.5 text-sm">
            <span className={gps ? "text-success" : "text-danger"}>
              {locating
                ? "Getting your location…"
                : gps
                  ? `✓ Location captured (±${gps.accuracy_m} m)`
                  : "✕ Location not available — required to submit"}
            </span>
            {!gps && !locating && (
              <Button type="button" variant="secondary" size="sm" onClick={captureGps}>
                Retry
              </Button>
            )}
          </div>
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
            <p className="mt-3 text-sm text-slate-500">
              Confirm identity, add observations and allow location access before submitting.
            </p>
          )}
          {submitError && <p className="mt-3 text-sm text-danger">{submitError}</p>}
        </Panel>
      </fieldset>
    </div>
  );
}
