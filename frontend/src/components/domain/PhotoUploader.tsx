import { useRef, useState } from "react";
import { useUploadPhoto } from "@/hooks/useData";
import { Button } from "@/components/ui/Button";

interface Props {
  photos: string[];
  onChange: (urls: string[]) => void;
}

// Uploads each file immediately via POST /uploads/photo and stores the
// returned Cloudinary URL — this is exactly what /inspections expects in
// its photos[] field, so there's no separate "attach" step later.
export function PhotoUploader({ photos, onChange }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadPhoto();
  const [failedCount, setFailedCount] = useState(0);

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setFailedCount(0);
    const urls: string[] = [];
    let failures = 0;
    for (const file of Array.from(files)) {
      try {
        const res = await upload.mutateAsync(file);
        urls.push(res.url);
      } catch {
        failures += 1;
      }
    }
    if (urls.length) onChange([...photos, ...urls]);
    setFailedCount(failures);
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-3 gap-3 sm:grid-cols-4">
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
          className="flex aspect-square flex-col items-center justify-center gap-1 rounded-md border border-dashed border-line text-xs text-slate-400 hover:border-teal hover:text-teal disabled:opacity-50"
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
