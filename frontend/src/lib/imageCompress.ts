// Shrinks big camera photos before upload. Phone cameras produce 3-10 MB JPEGs, but the
// backend rejects bodies over ~2 MB (and nginx over 3 MB). When nginx rejects a request
// it sends no CORS headers, so the browser reports it as a plain network failure
// (status 0) and the app keeps retrying forever. Compressing first avoids that entirely.
//
// Memory matters here. A 108 MP phone photo is ~430 MB once decoded at full size, which is
// enough for a low-RAM phone to kill the browser tab ("process stopped due to low memory")
// and drop the officer back to the sign-in page. So we never decode the full image: we read
// the pixel size from the JPEG header (a few KB), then ask the browser to decode it already
// scaled down to MAX_EDGE. Peak memory is then about 10 MB regardless of the camera.

const MAX_EDGE = 1600; // px, longest side; plenty for inspection evidence
const QUALITY = 0.8;
const SKIP_BELOW = 600 * 1024; // already small enough: leave untouched
const HEADER_BYTES = 512 * 1024; // the size and EXIF orientation are always near the start

export interface JpegInfo {
  width: number; // as stored (before EXIF rotation)
  height: number;
  orientation: number; // EXIF orientation 1-8 (1 = upright, also used when absent)
}

/** Reads pixel size and EXIF orientation from a JPEG's header bytes. Null if it isn't a readable JPEG. */
export function readJpegInfo(buf: ArrayBuffer): JpegInfo | null {
  const v = new DataView(buf);
  const len = v.byteLength;
  if (len < 4 || v.getUint16(0) !== 0xffd8) return null;

  let orientation = 1;
  let pos = 2;
  while (pos + 4 <= len) {
    if (v.getUint8(pos) !== 0xff) return null;
    const marker = v.getUint8(pos + 1);
    if (marker === 0xff) {
      pos += 1; // padding
      continue;
    }
    if (marker === 0xd8 || (marker >= 0xd0 && marker <= 0xd7) || marker === 0x01) {
      pos += 2; // markers without a length
      continue;
    }
    const size = v.getUint16(pos + 2);
    if (size < 2) return null;

    // SOF0-SOF15 except DHT (C4), JPG (C8) and DAC (CC) carry the frame size.
    if (marker >= 0xc0 && marker <= 0xcf && marker !== 0xc4 && marker !== 0xc8 && marker !== 0xcc) {
      if (pos + 9 > len) return null;
      const height = v.getUint16(pos + 5);
      const width = v.getUint16(pos + 7);
      return width > 0 && height > 0 ? { width, height, orientation } : null;
    }
    if (marker === 0xe1) orientation = readExifOrientation(v, pos + 4, Math.min(len, pos + 2 + size)) ?? orientation;
    if (marker === 0xda) return null; // start of scan: no frame header seen
    pos += 2 + size;
  }
  return null;
}

function readExifOrientation(v: DataView, start: number, end: number): number | null {
  // "Exif\0\0" then a TIFF header.
  if (start + 14 > end || v.getUint32(start) !== 0x45786966 || v.getUint16(start + 4) !== 0) return null;
  const tiff = start + 6;
  const little = v.getUint16(tiff) === 0x4949;
  if (!little && v.getUint16(tiff) !== 0x4d4d) return null;
  const u16 = (o: number) => v.getUint16(o, little);
  const u32 = (o: number) => v.getUint32(o, little);
  const ifd = tiff + u32(tiff + 4);
  if (ifd + 2 > end) return null;
  const count = u16(ifd);
  for (let i = 0; i < count; i++) {
    const entry = ifd + 2 + i * 12;
    if (entry + 12 > end) return null;
    if (u16(entry) === 0x0112) {
      const o = u16(entry + 8);
      return o >= 1 && o <= 8 ? o : null;
    }
  }
  return null;
}

// Canvas transform that turns a bitmap stored as `w` x `h` into an upright picture.
function applyOrientation(ctx: CanvasRenderingContext2D, orientation: number, w: number, h: number) {
  switch (orientation) {
    case 2: ctx.transform(-1, 0, 0, 1, w, 0); break;
    case 3: ctx.transform(-1, 0, 0, -1, w, h); break;
    case 4: ctx.transform(1, 0, 0, -1, 0, h); break;
    case 5: ctx.transform(0, 1, 1, 0, 0, 0); break;
    case 6: ctx.transform(0, 1, -1, 0, h, 0); break;
    case 7: ctx.transform(0, -1, -1, 0, h, w); break;
    case 8: ctx.transform(0, -1, 1, 0, 0, w); break;
    default: break;
  }
}

function toJpegFile(blob: Blob, original: File): File {
  const name = original.name.replace(/\.[^.]+$/, "") + ".jpg";
  return new File([blob], name, { type: "image/jpeg" });
}

function canvasToBlob(canvas: HTMLCanvasElement): Promise<Blob | null> {
  return new Promise((res) => canvas.toBlob(res, "image/jpeg", QUALITY));
}

/** Decodes a JPEG already scaled down, so the full-size picture never sits in memory. */
async function compressJpeg(file: File, info: JpegInfo): Promise<File | null> {
  const scale = Math.min(1, MAX_EDGE / Math.max(info.width, info.height));
  const sw = Math.max(1, Math.round(info.width * scale)); // size as stored, after scaling
  const sh = Math.max(1, Math.round(info.height * scale));

  // "none": we apply the EXIF rotation ourselves below, so the resize dimensions are
  // unambiguous (they are the stored ones) on every browser.
  const bitmap = await createImageBitmap(file, {
    imageOrientation: "none",
    resizeWidth: sw,
    resizeHeight: sh,
    resizeQuality: "medium",
  });
  const canvas = document.createElement("canvas");
  try {
    const rotated = info.orientation >= 5;
    canvas.width = rotated ? bitmap.height : bitmap.width;
    canvas.height = rotated ? bitmap.width : bitmap.height;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    applyOrientation(ctx, info.orientation, bitmap.width, bitmap.height);
    ctx.drawImage(bitmap, 0, 0);
    const blob = await canvasToBlob(canvas);
    return blob && blob.size < file.size ? toJpegFile(blob, file) : null;
  } finally {
    bitmap.close?.();
    canvas.width = canvas.height = 0; // hand the pixel buffer back right away
  }
}

/** Older path for anything that isn't a readable JPEG (PNG, HEIC, odd files). */
async function compressAny(file: File): Promise<File | null> {
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  const canvas = document.createElement("canvas");
  try {
    const scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height));
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await canvasToBlob(canvas);
    return blob && blob.size < file.size ? toJpegFile(blob, file) : null;
  } finally {
    bitmap.close?.();
    canvas.width = canvas.height = 0;
  }
}

export async function compressImage(file: File): Promise<File> {
  if (!file.type.startsWith("image/") || file.size <= SKIP_BELOW) return file;
  try {
    const info = readJpegInfo(await file.slice(0, HEADER_BYTES).arrayBuffer());
    if (info) {
      try {
        const out = await compressJpeg(file, info);
        if (out) return out;
      } catch {
        // The browser can't resize while decoding: use the general path below.
      }
    }
    return (await compressAny(file)) ?? file;
  } catch {
    return file; // unsupported format / decode error / out of memory: upload the original
  }
}