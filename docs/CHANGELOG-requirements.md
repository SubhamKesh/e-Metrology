# Requirements Tracker & Change Log

Tracks the gap-closing work against the Legal Metrology e-verification problem statement.
Updated after every change. Status: ✅ done · 🔧 in progress · ⬜ planned

## Roadmap

| # | Item | Status |
|---|------|--------|
| 1 | PWA foundation: service worker, offline page, install prompt, richer manifest, maskable icon | ✅ (code complete; needs device test) |
| 2 | In-app QR scanner on officer inspection page (+ GPS stamp) | ⬜ |
| 3 | Offline-capable inspection with background sync | ⬜ |
| 4 | Re-verification flow (application type, link to previous certificate, Renew button) | ⬜ |
| 5 | Real scheduling (admin/LMO allocation, date + slot, reschedule) | ⬜ |
| 6 | Richer inspection form (per-instrument parameters, stamp/seal number) | ⬜ |
| 7 | Search + CSV/PDF report export | ⬜ |
| 8 | Dashboards: pendency ageing, district-wise, enforcement module | ⬜ |
| 9 | Configurable validity per instrument type | ⬜ |
| 10 | Owner supporting-document upload, profile editing | ⬜ |
| 11 | SMS / WhatsApp alerts | ⬜ |
| 12 | Consolidated architecture / security / deployment document | ⬜ |

## Log

### 2026-10-14 — #1 PWA foundation
**Added**
- `frontend/public/sw.js` — service worker. Caches only static app files (hashed `/assets/*`, fonts, icons). Never touches `/api/*`, WebSockets, non-GET requests or PDFs, so no personal or certificate data is stored. Navigations are network-first with `offline.html` fallback.
- `frontend/public/offline.html` — offline fallback page.
- `frontend/src/lib/pwa.ts` — `registerServiceWorker()` (production only) and `useInstallPrompt()` hook (Android/desktop `beforeinstallprompt`, iOS "Add to Home Screen" hint).
- `frontend/src/components/ui/InstallBanner.tsx` — dismissible install banner.

**Changed**
- `frontend/src/main.tsx` — registers the service worker.
- `frontend/src/components/layout/AppShell.tsx` — shows `InstallBanner` above page content.
- `frontend/public/site.webmanifest` — added `id`, `orientation`, `lang`, `categories`, shortcuts (Verify a certificate, Sign in).
- `frontend/index.html` — `theme-color`, iOS web-app meta tags, `viewport-fit=cover`.
- `frontend/vercel.json` — no-cache header for `sw.js`, short cache for the manifest.

**Completed in the follow-up pass (same step)**
- `frontend/public/icon-maskable-512.png` — new maskable icon (logo inside the 60% safe zone) and added to the manifest with `purpose: "maskable"`.
- `frontend/scripts/generate-assets.mjs` — now emits the maskable icon and the full new manifest, so regenerating icons no longer reverts the manifest.
- `render.yaml` — Render is the real static host, so added headers there: `/sw.js` no-cache, `/offline.html` no-cache, `/site.webmanifest` 1 hour. (`vercel.json` kept in sync.)
- `InstallBanner.tsx` — fixed button colours to use classes that exist in the Tailwind palette (`bg-teal`, `hover:bg-teal-600`).
- Checked: `sw.js` and the generator pass `node --check`; manifest, `vercel.json` and `render.yaml` parse as valid JSON/YAML.

**Notes**
- Not built or run on a device (no network for `npm install` in the authoring environment). Test with `npm ci && npm run build && npm run preview`, then Chrome DevTools → Application → Manifest / Service Workers, and use the "Offline" toggle.
- Offline data entry is deliberately not part of this step (see #3).
- Pre-existing, unrelated to this change: `scripts/prerender.mjs` expects `<!-- seo:head -->` markers in `index.html`, which the file doesn't contain, and `npm run build` doesn't call prerender. Not touched.
