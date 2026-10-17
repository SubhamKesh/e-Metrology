// Shrinks big camera photos before upload. Phone cameras produce 3-10 MB JPEGs, but the
// backend rejects bodies over ~2 MB (and nginx over 3 MB). When nginx rejects a request
// it sends no CORS headers, so the browser reports it as a plain network failure
// (status 0) and the app keeps retrying forever. Compressing first avoids that entirely.

const MAX_EDGE = 1600; // px, longest side; plenty for inspection evidence
const QUALITY = 0.8;
const SKIP_BELOW = 600 * 1024; // already small enough: leave untouched

export async function compressImage(file: File): Promise<File> {
  if (!file.type.startsWith("image/") || file.size <= SKIP_BELOW) return file;
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    const scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height));
    const w = Math.max(1, Math.round(bitmap.width * scale));
    const h = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return file;
    ctx.drawImage(bitmap, 0, 0, w, h);
    bitmap.close?.();
    const blob = await new Promise<Blob | null>((res) => canvas.toBlob(res, "image/jpeg", QUALITY));
    if (!blob || blob.size >= file.size) return file;
    const name = file.name.replace(/\.[^.]+$/, "") + ".jpg";
    return new File([blob], name, { type: "image/jpeg" });
  } catch {
    return file; // unsupported format / decode error: upload the original
  }
}
