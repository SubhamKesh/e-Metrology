/**
 * One-off generator for the files in public/ (favicon set, touch icons, og-image.png).
 * The generated files are committed, so this is NOT part of `npm run build`.
 *
 *   npm i --no-save sharp && node scripts/generate-assets.mjs
 *
 * Colours come from tailwind.config.js (paper, ink, teal, brass, slate).
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

const C = { paper: "#F6F4EE", ink: "#14181C", teal: "#1F5F5B", brass: "#B08D3E", slate: "#3D4A52", navy: "#0d3a59", gold: "#b88f4b", cream: "#f7f1e6" };

// Same artwork as src/components/ui/Brand.tsx (BrandMark), viewBox 0 0 100 100.
const markInner = `
  <circle cx="50" cy="50" r="44" fill="${C.cream}" stroke="${C.navy}" stroke-width="7"/>
  <circle cx="50" cy="50" r="36" fill="none" stroke="${C.gold}" stroke-width="3" opacity="0.9"/>
  <g stroke="${C.gold}" stroke-linecap="round" stroke-width="2.5">
    <path d="M25 36 L50 60 L75 36" fill="none"/>
    <path d="M50 60 L50 33" fill="none"/>
    <path d="M15 68 H85" stroke="${C.navy}" stroke-width="4"/>
    <path d="M20 76 L33 68 H67 L80 76" fill="none" stroke="${C.navy}" stroke-width="4"/>
  </g>
  <g fill="${C.navy}">
    <rect x="46" y="18" width="8" height="12" rx="2"/>
    <path d="M50 10 L54 18 H46 Z"/>
  </g>
  <path d="M50 18 L50 82" stroke="${C.navy}" stroke-width="2" opacity="0.7"/>`;

const faviconSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">${markInner}</svg>\n`;
writeFileSync(out("favicon.svg"), faviconSvg);

const markOnPaper = (size, pad) => `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
  <rect width="${size}" height="${size}" fill="${C.paper}"/>
  <g transform="translate(${pad} ${pad}) scale(${(size - pad * 2) / 100})">${markInner}</g>
</svg>`;

const png = (svg, size) => sharp(Buffer.from(svg)).resize(size, size).png().toBuffer();

// Touch / manifest icons
writeFileSync(out("apple-touch-icon.png"), await png(markOnPaper(180, 18), 180));
writeFileSync(out("icon-192.png"), await png(markOnPaper(192, 20), 192));
writeFileSync(out("icon-512.png"), await png(markOnPaper(512, 52), 512));

// favicon.ico: PNG-compressed 16/32/48 images in an ICO container.
const sizes = [16, 32, 48];
const imgs = await Promise.all(sizes.map((s) => sharp(Buffer.from(faviconSvg)).resize(s, s).png().toBuffer()));
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

// Open Graph / Twitter preview, 1200x630
const serif = "'Source Serif 4', Georgia, 'Liberation Serif', serif";
const sans = "Inter, 'Liberation Sans', Arial, sans-serif";
const ogSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <rect width="1200" height="630" fill="${C.paper}"/>
  <rect x="0" y="0" width="16" height="630" fill="${C.teal}"/>
  <rect x="0" y="600" width="1200" height="30" fill="${C.ink}"/>
  <rect x="80" y="568" width="120" height="4" fill="${C.brass}"/>
  <g transform="translate(80 70) scale(1.3)">${markInner}</g>
  <text x="232" y="158" font-family="${serif}" font-size="64" font-weight="600" fill="${C.ink}">MaapSetu</text>
  <text x="80" y="330" font-family="${serif}" font-size="70" font-weight="600" fill="${C.ink}">Legal Metrology verification</text>
  <text x="80" y="412" font-family="${serif}" font-size="56" font-weight="400" fill="${C.teal}">for weighing and measuring instruments</text>
  <text x="80" y="500" font-family="${sans}" font-size="30" fill="${C.slate}">Register online. Get a QR-verifiable digital certificate. Check it in seconds.</text>
  <text x="80" y="548" font-family="${sans}" font-size="26" fill="${C.slate}" opacity="0.85">Digital Legal Metrology platform for India</text>
</svg>`;
writeFileSync(out("og-image.png"), await sharp(Buffer.from(ogSvg)).png({ compressionLevel: 9 }).toBuffer());

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
      background_color: C.paper,
      theme_color: C.teal,
      icons: [
        { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
        { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
      ],
    },
    null,
    2,
  ) + "\n",
);
console.log("public/ assets written");
