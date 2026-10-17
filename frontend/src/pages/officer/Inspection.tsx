import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/AppShell";
import { Panel } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { TextArea, TextInput } from "@/components/ui/Field";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { PhotoUploader } from "@/components/domain/PhotoUploader";
import { QrScanner } from "@/components/domain/QrScanner";
import { getGpsFix, type GpsFix } from "@/lib/geo";
import { useApplication, useInspectionFormSpec, useInstrument, useSubmitInspection } from "@/hooks/useData";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useQueuedInspections } from "@/hooks/useOfflineSync";
import { enqueueInspection } from "@/lib/offlineQueue";
import { deleteDraft, isDraftEmpty, loadDraft, saveDraft, type InspectionDraft } from "@/lib/offlineDrafts";
import type { IdentityMethod, InspectionResult, Role } from "@/lib/types";
import { cn } from "@/lib/cn";

// A draft older than this keeps its notes and photos, but the officer must tick the
// "physically confirmed" box again: that confirmation belongs to the visit it was made on.
const RECONFIRM_AFTER_MS = 12 * 60 * 60 * 1000;

const SEAL_RE = /^[A-Z0-9][A-Z0-9 /._-]{2,31}$/;
const normalizeSeal = (v: string) => v.trim().replace(/\s+/g, " ").toUpperCase();

/** A typed reading as a number, or null if it isn't one. */
function parseReading(v: string): number | null {
  const t = v.trim().replace(",", ".");
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) && Math.abs(n) <= 1e9 ? n : null;
}

const fmtNum = (n: number) => (Math.abs(n) >= 1000 || Number.isInteger(n) ? String(n) : String(Number(n.toFixed(4))));

const fmtWhen = (ms: number) =>
  new Date(ms).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export function InspectionWorkflow({ role }: { role: Extract<Role, "lmo" | "gatc"> }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data: application, isLoading, error, refetch } = useApplication(id);
  const { data: instrument } = useInstrument(application?.instrument_id);
  const submit = useSubmitInspection();
  const { data: spec, isLoading: specLoading, refetch: refetchSpec } = useInspectionFormSpec(instrument?.type);
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
  const [readings, setReadings] = useState<{ reference: string; indicated: string }[]>([]);
  const [checks, setChecks] = useState<Record<string, boolean>>({});
  const [sealNumber, setSealNumber] = useState("");
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

  // ---- Draft: everything entered so far is kept on this device and restored on return ----
  const [draftLoaded, setDraftLoaded] = useState(false);
  const [resumedAt, setResumedAt] = useState<number | null>(null);
  const [draftSavedAt, setDraftSavedAt] = useState<number | null>(null);
  const submittedRef = useRef(false); // once submitted/queued, the draft must not be written again
  const loadedRef = useRef(false);
  const latest = useRef<InspectionDraft | null>(null);

  const draft: InspectionDraft | null =
    user?.id && id
      ? {
          application_id: id,
          user_id: user.id,
          client_id: clientId.current,
          label: instrument ? `${instrument.type} · ${instrument.manufacturer} ${instrument.model}` : `Application ${id}`,
          entered_serial: enteredSerial,
          identity_method: identityMethod,
          serial_confirmed: serialConfirmed,
          photos,
          pending_photos: pendingPhotos.map((f) => ({ name: f.name, type: f.type, blob: f })),
          observations,
          readings,
          checks,
          seal_number: sealNumber,
          updated_at: Date.now(),
        }
      : null;

  useEffect(() => {
    latest.current = draft;
    loadedRef.current = draftLoaded;
  });

  // Restore a saved draft for this application, once.
  useEffect(() => {
    if (!user?.id || !id) return;
    let cancelled = false;
    loadDraft(user.id, id)
      .then((d) => {
        if (cancelled) return;
        if (d) {
          clientId.current = d.client_id;
          setEnteredSerial(d.entered_serial);
          setIdentityMethod(d.identity_method);
          setSerialConfirmed(d.serial_confirmed && Date.now() - d.updated_at < RECONFIRM_AFTER_MS);
          setPhotos(d.photos);
          setPendingPhotos(d.pending_photos.map((p) => new File([p.blob], p.name, { type: p.type })));
          setObservations(d.observations);
          setReadings(d.readings ?? []);
          setChecks(d.checks ?? {});
          setSealNumber(d.seal_number ?? "");
          setResumedAt(d.updated_at);
        }
        setDraftLoaded(true);
      })
      .catch(() => {
        if (!cancelled) setDraftLoaded(true); // storage trouble: carry on without drafts
      });
    return () => {
      cancelled = true;
    };
  }, [user?.id, id]);

  // A fresh form starts with the minimum number of empty reading rows for this instrument type.
  const seededRef = useRef(false);
  useEffect(() => {
    if (!draftLoaded || !spec || seededRef.current) return;
    seededRef.current = true;
    setReadings((cur) => (cur.length > 0 ? cur : Array.from({ length: spec.test.min_points }, () => ({ reference: "", indicated: "" }))));
  }, [draftLoaded, spec]);

  // Auto-save shortly after every change.
  useEffect(() => {
    if (!draftLoaded) return;
    const t = setTimeout(() => {
      const d = latest.current;
      if (!d || submittedRef.current) return;
      saveDraft(d)
        .then(() => setDraftSavedAt(isDraftEmpty(d) ? null : Date.now()))
        .catch(() => {});
    }, 800);
    return () => clearTimeout(t);
  }, [draftLoaded, observations, enteredSerial, identityMethod, serialConfirmed, photos, pendingPhotos, instrument, readings, checks, sealNumber]);

  // Save immediately when the officer leaves the page or switches app, so the last few seconds aren't lost.
  useEffect(() => {
    const flush = () => {
      const d = latest.current;
      if (d && loadedRef.current && !submittedRef.current) saveDraft(d).catch(() => {});
    };
    const onHide = () => document.visibilityState === "hidden" && flush();
    document.addEventListener("visibilitychange", onHide);
    window.addEventListener("pagehide", flush);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      window.removeEventListener("pagehide", flush);
      flush();
    };
  }, []);

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

  // ---- Detailed form: what is complete, what is still missing ----
  const rows = readings.map((r) => ({ ref: parseReading(r.reference), ind: parseReading(r.indicated), raw: r }));
  const touched = rows.filter((r) => r.raw.reference.trim() !== "" || r.raw.indicated.trim() !== "");
  const incompleteRows = touched.filter((r) => r.ref === null || r.ind === null).length;
  const validPoints = touched.filter((r) => r.ref !== null && r.ind !== null).map((r) => ({ reference: r.ref as number, indicated: r.ind as number }));
  const sealNorm = normalizeSeal(sealNumber);
  const sealValid = SEAL_RE.test(sealNorm);
  const missingForPass: string[] = [];
  if (!spec) {
    missingForPass.push("the checklist for this instrument (couldn't be loaded)");
  } else {
    if (validPoints.length < spec.test.min_points) {
      missingForPass.push(`at least ${spec.test.min_points} test reading${spec.test.min_points === 1 ? "" : "s"}`);
    }
    if (spec.checks.some((c) => checks[c.key] === undefined)) missingForPass.push("an answer to every check");
    else if (spec.checks.some((c) => c.required && checks[c.key] !== true)) missingForPass.push("every required check met (record this as a Fail instead)");
    if (!sealValid) missingForPass.push("the seal number (3-32 letters or digits)");
  }

  const serialMatches = instrument ? enteredSerial.trim() === instrument.uiid : false;
  const identityBlocked = enteredSerial.length > 0 && !serialMatches;

  // The inspection is now sent or safely in the send queue: the draft has done its job.
  async function finishDraft() {
    submittedRef.current = true;
    if (user && id) await deleteDraft(user.id, id).catch(() => {});
  }

  async function discardDraft() {
    if (!user || !id) return;
    await deleteDraft(user.id, id).catch(() => {});
    clientId.current = crypto.randomUUID();
    setEnteredSerial("");
    setIdentityMethod("manual");
    setSerialConfirmed(false);
    setPhotos([]);
    setPendingPhotos([]);
    setObservations("");
    seededRef.current = false;
    setReadings([]);
    setChecks({});
    setSealNumber("");
    setResult(null);
    setSubmitError(null);
    setResumedAt(null);
    setDraftSavedAt(null);
  }

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
      // A seal is only fixed on a passed instrument, so a Fail never carries one.
      const detail = {
        test_points: validPoints.length > 0 ? validPoints : undefined,
        checks: Object.keys(checks).length > 0 ? checks : undefined,
        seal_number: finalResult === "pass" ? sealNorm : undefined,
      };

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
          ...detail,
        });
        await finishDraft();
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
          ...detail,
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
      await finishDraft();
      navigate(`/app/${role}/applications/${id}`);
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : "Couldn't submit this inspection. Try again.");
    }
  }

  const canFail = serialConfirmed && serialMatches && observations.trim().length > 0 && !!gps && incompleteRows === 0;
  const canPass = canFail && missingForPass.length === 0;

  return (
    <div className="max-w-2xl">
      <PageHeader title="Field verification" description={instrument ? `${instrument.type} · ${instrument.manufacturer} ${instrument.model}` : undefined} />

      {(resumedAt || draftSavedAt) && (
        <div className="mb-4 flex items-center justify-between gap-3 rounded-lg border border-line bg-white px-4 py-3 text-sm shadow-sm">
          <p className="text-ink">
            {resumedAt ? "Resumed your draft. " : ""}
            Saved automatically on this device{draftSavedAt ?? resumedAt ? ` · ${fmtWhen((draftSavedAt ?? resumedAt) as number)}` : ""}.
          </p>
          <button type="button" onClick={discardDraft} className="shrink-0 font-medium text-danger underline">
            Start over
          </button>
        </div>
      )}

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
          <h2 className="mb-1 text-sm font-medium text-ink">3. {spec?.test.title ?? "Test readings"}</h2>
          {spec ? (
            <>
              <p className="mb-3 text-sm text-slate-500">
                {spec.test.hint} Needs at least {spec.test.min_points} for a Pass. Values in {spec.test.unit}.
              </p>
              <div className="space-y-3">
                {readings.map((row, i) => {
                  const ref = parseReading(row.reference);
                  const ind = parseReading(row.indicated);
                  const err = ref !== null && ind !== null ? ind - ref : null;
                  return (
                    <div key={i} className="grid grid-cols-[1fr_1fr_auto] items-end gap-3 sm:grid-cols-[1fr_1fr_8rem_auto]">
                      <div>
                        <label htmlFor={`ref-${i}`} className="text-xs text-slate-500">
                          {spec.test.reference_label}
                        </label>
                        <input
                          id={`ref-${i}`}
                          inputMode="decimal"
                          value={row.reference}
                          onChange={(e) => setReadings((rs) => rs.map((r, j) => (j === i ? { ...r, reference: e.target.value } : r)))}
                          className="mt-1 h-10 w-full rounded-md border border-line px-3 text-sm focus:outline-none focus:ring-2 focus:ring-teal/30"
                        />
                      </div>
                      <div>
                        <label htmlFor={`ind-${i}`} className="text-xs text-slate-500">
                          {spec.test.indicated_label}
                        </label>
                        <input
                          id={`ind-${i}`}
                          inputMode="decimal"
                          value={row.indicated}
                          onChange={(e) => setReadings((rs) => rs.map((r, j) => (j === i ? { ...r, indicated: e.target.value } : r)))}
                          className="mt-1 h-10 w-full rounded-md border border-line px-3 text-sm focus:outline-none focus:ring-2 focus:ring-teal/30"
                        />
                      </div>
                      <p className="col-span-2 text-xs text-slate-500 sm:col-span-1 sm:pb-2.5">
                        {err === null
                          ? "Error: —"
                          : `Error: ${err > 0 ? "+" : ""}${fmtNum(err)} ${spec.test.unit}${ref ? ` (${err > 0 ? "+" : ""}${fmtNum((err / ref) * 100)}%)` : ""}`}
                      </p>
                      <button
                        type="button"
                        aria-label={`Remove reading ${i + 1}`}
                        disabled={readings.length <= 1}
                        onClick={() => setReadings((rs) => rs.filter((_, j) => j !== i))}
                        className="mb-1 h-8 rounded px-2 text-sm text-slate-500 hover:text-danger disabled:opacity-30"
                      >
                        ✕
                      </button>
                    </div>
                  );
                })}
              </div>
              {incompleteRows > 0 && (
                <p className="mt-3 text-sm text-danger">Fill in both values as numbers, or clear the row, before submitting.</p>
              )}
              <Button
                type="button"
                variant="secondary"
                size="sm"
                className="mt-3"
                disabled={readings.length >= spec.test.max_points}
                onClick={() => setReadings((rs) => [...rs, { reference: "", indicated: "" }])}
              >
                Add reading
              </Button>
              <p className="mt-3 text-xs text-slate-500">
                The error is worked out for you. Whether it is within the permitted limit is your call: record the result below.
              </p>
            </>
          ) : specLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : (
            <div className="rounded-md bg-danger-50 px-4 py-3 text-sm text-danger">
              Couldn't load the test readings and checks for this instrument. You can still record a Fail with notes; a Pass needs them.
              <button type="button" onClick={() => refetchSpec()} className="ml-2 font-medium underline">
                Retry
              </button>
            </div>
          )}
        </Panel>

        {spec && (
          <Panel className="mb-5 p-5">
            <h2 className="mb-3 text-sm font-medium text-ink">4. Checks</h2>
            <ul className="divide-y divide-line">
              {spec.checks.map((c) => (
                <li key={c.key} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
                  <span className="text-sm text-ink">
                    {c.label}
                    {c.required && <span className="text-danger"> *</span>}
                  </span>
                  <div role="radiogroup" aria-label={c.label} className="flex shrink-0 gap-2">
                    {([true, false] as const).map((val) => (
                      <button
                        key={String(val)}
                        type="button"
                        role="radio"
                        aria-checked={checks[c.key] === val}
                        onClick={() => setChecks((cs) => ({ ...cs, [c.key]: val }))}
                        className={cn(
                          "h-9 min-w-16 rounded-md border px-3 text-sm font-medium",
                          checks[c.key] === val
                            ? val
                              ? "border-success bg-success-50 text-success"
                              : "border-danger bg-danger-50 text-danger"
                            : "border-line bg-white text-slate-600 hover:bg-paper2/60",
                        )}
                      >
                        {val ? "Yes" : "No"}
                      </button>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-slate-500">* Must be Yes for a Pass.</p>
          </Panel>
        )}

        <Panel className="mb-5 p-5">
          <h2 className="mb-3 text-sm font-medium text-ink">{spec ? "5" : "4"}. Observations</h2>
          <TextArea
            label="Inspection notes"
            placeholder="Describe what was checked and what was found."
            value={observations}
            onChange={(e) => setObservations(e.target.value)}
            required
          />
        </Panel>

        <Panel className="p-5">
          <h2 className="mb-3 text-sm font-medium text-ink">{spec ? "6" : "5"}. Result</h2>
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
          <div className="mb-4">
            <TextInput
              label={spec?.seal.label ?? "Verification stamp / seal number"}
              value={sealNumber}
              onChange={(e) => setSealNumber(e.target.value)}
              placeholder="Number on the seal you fixed"
              autoCapitalize="characters"
              autoComplete="off"
              error={sealNumber.trim() !== "" && !sealValid ? "3-32 characters: letters, digits, space and / . _ -" : undefined}
              hint="Fix the seal on the instrument, then enter its number. Needed for a Pass; leave blank for a Fail."
            />
          </div>
          <div className="flex flex-col gap-3 sm:flex-row">
            <Button
              type="button"
              className="flex-1"
              loading={submit.isPending && result === "pass"}
              disabled={!canPass || submit.isPending}
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
              disabled={!canFail || submit.isPending}
              onClick={() => {
                setResult("fail");
                onSubmit("fail");
              }}
            >
              Submit — Fail
            </Button>
          </div>
          {!canFail ? (
            <p className="mt-3 text-sm text-slate-500">
              Confirm identity, add observations and allow location access before submitting.
            </p>
          ) : (
            missingForPass.length > 0 && <p className="mt-3 text-sm text-slate-500">To pass this instrument you still need: {missingForPass.join("; ")}.</p>
          )}
          {submitError && <p className="mt-3 text-sm text-danger">{submitError}</p>}
        </Panel>
      </fieldset>
    </div>
  );
}