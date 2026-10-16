import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import { useUploadPhoto } from "@/hooks/useData";
import { Button } from "@/components/ui/Button";

interface Props {
  photos: string[];
  onChange: (urls: string[]) => void;
  // Optional offline support: when the upload fails because there's no connection, the
  // photo is kept here (on the device) instead of being lost, and uploaded at sync time.
  pending?: File[];
  onPendingChange?: (files: File[]) => void;
}

// Uploads each file immediately via POST /uploads/photo and stores the
// returned Cloudinary URL — this is exactly what /inspections expects in
// its photos[] field, so there's no separate "attach" step later.
export function PhotoUploader({ photos, onChange, pending = [], onPendingChange }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadPhoto();
  const [failedCount, setFailedCount] = useState(0);

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setFailedCount(0);
    const urls: string[] = [];
    const kept: File[] = [];
    let failures = 0;
    for (const file of Array.from(files)) {
      try {
        const res = await upload.mutateAsync(file);
        urls.push(res.url);
      } catch (err) {
        if (onPendingChange && err instanceof ApiError && err.status === 0) kept.push(file);
        else failures += 1;
      }
    }
    if (urls.length) onChange([...photos, ...urls]);
    if (kept.length) onPendingChange?.([...pending, ...kept]);
    setFailedCount(failures);
    if (inputRef.current) inputRef.current.value = "";
  }

  const pendingUrls = useMemo(() => pending.map((f) => URL.createObjectURL(f)), [pending]);
  useEffect(() => () => pendingUrls.forEach((u) => URL.revokeObjectURL(u)), [pendingUrls]);

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-3 gap-3 sm:grid-cols-4">
        {pendingUrls.map((url, i) => (
          <div key={url} className="group relative aspect-square overflow-hidden rounded-md border border-dashed border-teal">
            <img src={url} alt="Verification evidence, saved on this device" className="h-full w-full object-cover" />
            <span className="absolute bottom-1 left-1 rounded bg-ink/70 px-1.5 py-0.5 text-[10px] text-white">Saved offline</span>
            <button
              type="button"
              onClick={() => onPendingChange?.(pending.filter((_, j) => j !== i))}
              className="absolute right-1 top-1 hidden h-6 w-6 items-center justify-center rounded-full bg-ink/70 text-xs text-white group-hover:flex"
              aria-label="Remove photo"
            >
              ✕
            </button>
          </div>
        ))}
        {photos.map((url) => (
          <div key={url} className="group relative aspect-square overflow-hidden rounded-md border border-line">
            <img src={url} alt="Verification evidence" className="h-full w-full object-cover" />
            <button
              type="button"
              onClick={() => onChange(photos.filter((p) => p !== url))}
              className="absolute right-1 top-1 hidden h-6 w-6 items-center justify-center rounded-full bg-ink/70 text-xs text-white group-hover:flex"
              aria-label="Remove photo"
            >
              ✕
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={upload.isPending}
          className="flex aspect-square flex-col items-center justify-center gap-1 rounded-md border border-dashed border-line text-xs text-slate-500 hover:border-teal hover:text-teal disabled:opacity-50"
        >
          <span className="text-xl leading-none">+</span>
          {upload.isPending ? "Uploading…" : "Add photo"}
        </button>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        capture="environment"
        multiple
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />
      {failedCount > 0 && (
        <p className="text-sm text-danger">
          {failedCount} photo{failedCount > 1 ? "s" : ""} failed to upload. Try again.
        </p>
      )}
      <Button type="button" variant="secondary" size="sm" onClick={() => inputRef.current?.click()}>
        {photos.length === 0 ? "Add photos" : "Add more photos"}
      </Button>
    </div>
  );
}
