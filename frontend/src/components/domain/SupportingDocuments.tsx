import { useEffect, useRef, useState } from "react";
import { Panel } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ApiError } from "@/lib/api";
import { useInstrumentDocuments, useRemoveDocument, useUploadDocument } from "@/hooks/useData";
import type { DocumentSlot } from "@/lib/types";

const MAX_BYTES = 5 * 1024 * 1024;

function sizeText(bytes: number) {
  return bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/**
 * The documents an instrument's application needs: Tax invoice + Owner ID proof for a first
 * verification, the Previous certificate for a re-verification. One file per slot; uploading again
 * replaces it. The owner uploads them (`readOnly` is false); officers and admins only see them.
 * `onStatus` reports whether every required document is in, so the apply form can hold the Submit button.
 */
export function SupportingDocuments({
  instrumentId,
  readOnly = false,
  onStatus,
  bare = false,
}: {
  instrumentId: string;
  readOnly?: boolean;
  onStatus?: (status: { complete: boolean; loading: boolean }) => void;
  /** Render without the surrounding panel (when it sits inside another card). */
  bare?: boolean;
}) {
  const { data, isLoading, isError } = useInstrumentDocuments(instrumentId);
  const upload = useUploadDocument(instrumentId);
  const remove = useRemoveDocument(instrumentId);
  const inputRef = useRef<HTMLInputElement>(null);
  const [pickFor, setPickFor] = useState<DocumentSlot | null>(null);
  const [busy, setBusy] = useState<DocumentSlot | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const complete = !!data?.complete;
  useEffect(() => {
    onStatus?.({ complete, loading: isLoading });
  }, [complete, isLoading, onStatus]);

  async function onPick(files: FileList | null) {
    const file = files?.[0];
    const slot = pickFor;
    if (inputRef.current) inputRef.current.value = "";
    if (!file || !slot) return;
    setMessage(null);
    if (file.size > MAX_BYTES) {
      setMessage("That file is larger than 5 MB. Choose a smaller PDF, JPG or PNG.");
      return;
    }
    setBusy(slot);
    try {
      await upload.mutateAsync({ slot, file });
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "The document could not be uploaded. Try again.");
    } finally {
      setBusy(null);
    }
  }

  async function onRemove(slot: DocumentSlot) {
    setMessage(null);
    setBusy(slot);
    try {
      await remove.mutateAsync(slot);
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "The document could not be removed. Try again.");
    } finally {
      setBusy(null);
    }
  }

  // Officers and admins who cannot see this instrument's documents just see nothing.
  if (isError && readOnly) return null;

  const locked = !!data?.locked;
  // Read-only views list what was uploaded; the owner sees every required slot, filled or not.
  const slots = (data?.slots ?? []).filter((s) => !readOnly || s.document || s.required);

  const body = (
    <>
      <h2 className="mb-1 text-sm font-medium text-ink">
        {readOnly ? "Documents" : data?.application_type === "renewal" ? "Documents for re-verification" : "Documents required to apply"}
      </h2>
      {!readOnly && (
        <p className="mb-3 text-xs text-slate-500">
          {locked
            ? "An application is in progress for this instrument, so its documents can't be changed."
            : "All of these are required before you can submit. PDF, JPG or PNG, up to 5 MB each."}
        </p>
      )}

      {isLoading ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : isError ? (
        <p className="text-sm text-danger">Documents could not be loaded.</p>
      ) : (
        <ul className="divide-y divide-line rounded-lg border border-line">
          {slots.map((s) => (
            <li key={s.slot} className="flex flex-col gap-2 px-3 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="font-medium text-ink">
                  {s.label}
                  {s.required && !readOnly && <span className="text-danger"> *</span>}
                </p>
                {s.document ? (
                  <p className="text-xs text-slate-500">
                    <a
                      href={s.document.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-medium text-teal hover:underline"
                    >
                      {s.document.filename}
                    </a>{" "}
                    · {sizeText(s.document.size)} ·{" "}
                    {new Date(s.document.uploaded_at).toLocaleDateString("en-IN", { dateStyle: "medium" })}
                  </p>
                ) : (
                  <p className="text-xs text-slate-500">{readOnly ? "Not provided" : s.hint}</p>
                )}
              </div>
              {!readOnly && (
                <div className="flex shrink-0 gap-2">
                  <Button
                    type="button"
                    variant={s.document ? "secondary" : "primary"}
                    size="sm"
                    loading={busy === s.slot && upload.isPending}
                    disabled={locked || busy !== null}
                    onClick={() => {
                      setPickFor(s.slot);
                      inputRef.current?.click();
                    }}
                  >
                    {s.document ? "Replace" : "Upload"}
                  </Button>
                  {s.document && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={locked || busy !== null}
                      onClick={() => onRemove(s.slot)}
                      aria-label={`Remove ${s.label}`}
                    >
                      Remove
                    </Button>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {!readOnly && (
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,image/jpeg,image/png"
          className="hidden"
          onChange={(e) => onPick(e.target.files)}
        />
      )}
      {message && (
        <p role="alert" className="mt-3 text-sm text-danger">
          {message}
        </p>
      )}
    </>
  );

  return bare ? <div>{body}</div> : <Panel className="mb-6 p-4 sm:p-5">{body}</Panel>;
}
