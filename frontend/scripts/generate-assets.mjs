/**
 * One-off generator for the icon files in public/ (favicon set, touch icons, manifest).
 * The generated files are committed, so this is NOT part of `npm run build`.
 *
 *   npm i --no-save sharp && node scripts/generate-assets.mjs
 *
 * Source artwork: public/logo-mark.png (the MaapSetu logo mark, transparent background).
 * public/logo-full.png (full lock-up) and public/og-image.png (1200x630 social preview) are
 * static design assets: replace them by hand when the logo changes.
 */
import { writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

let sharp;
try {
  sharp = (await import("sharp")).default;
} catch {
  console.error("sharp is required: run `npm i --no-save sharp` first.");
  process.exit(1);
}

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const out = (f) => resolve(root, "public", f);
mkdirSync(resolve(root, "public"), { recursive: true });

const MARK = out("logo-mark.png");
const WHITE = { r: 255, g: 255, b: 255, alpha: 1 };
const CLEAR = { r: 0, g: 0, b: 0, alpha: 0 };

/** The mark centred on a square canvas, `padRatio` of the side kept free on every edge. */
async function squareIcon(size, padRatio, background) {
  const inner = Math.round(size * (1 - 2 * padRatio));
  const mark = await sharp(MARK).resize(inner, inner, { fit: "contain", background: CLEAR }).png().toBuffer();
  return sharp({ create: { width: size, height: size, channels: 4, background } })
    .composite([{ input: mark, gravity: "center" }])
    .png({ compressionLevel: 9 })
    .toBuffer();
}

// Touch / manifest icons
writeFileSync(out("apple-touch-icon.png"), await squareIcon(180, 0.1, WHITE));
writeFileSync(out("icon-192.png"), await squareIcon(192, 0.1, WHITE));
writeFileSync(out("icon-512.png"), await squareIcon(512, 0.12, WHITE));

// favicon.svg: wraps the PNG mark so it always matches the logo exactly.
const faviconPng = await squareIcon(128, 0.03, CLEAR);
writeFileSync(
  out("favicon.svg"),
  `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 128 128"><image width="128" height="128" xlink:href="data:image/png;base64,${faviconPng.toString("base64")}"/></svg>\n`,
);

// favicon.ico: PNG-compressed 16/32/48 images in an ICO container.
const sizes = [16, 32, 48];
const imgs = await Promise.all(sizes.map((s) => squareIcon(s, 0.03, CLEAR)));
const header = Buffer.alloc(6);
header.writeUInt16LE(0, 0);
header.writeUInt16LE(1, 2);
header.writeUInt16LE(imgs.length, 4);
let offset = 6 + 16 * imgs.length;
const entries = imgs.map((buf, i) => {
  const e = Buffer.alloc(16);
  e.writeUInt8(sizes[i], 0);
  e.writeUInt8(sizes[i], 1);
  e.writeUInt16LE(1, 4);
  e.writeUInt16LE(32, 6);
  e.writeUInt32LE(buf.length, 8);
  e.writeUInt32LE(offset, 12);
  offset += buf.length;
  return e;
});
writeFileSync(out("favicon.ico"), Buffer.concat([header, ...entries, ...imgs]));

writeFileSync(
  out("site.webmanifest"),
  JSON.stringify(
    {
      name: "MaapSetu",
      short_name: "MaapSetu",
      description: "Digital Legal Metrology verification and certification for weighing and measuring instruments in India.",
      start_url: "/",
      scope: "/",
      display: "standalone",
      background_color: "#F6F4EE",
      theme_color: "#1F5F5B",
      icons: [
        { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
        { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
      ],
    },
    null,
    2,
  ) + "\n",
);
console.log("public/ icon assets written");
