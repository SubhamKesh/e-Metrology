# Requirements Tracker & Change Log

Tracks the gap-closing work against the Legal Metrology e-verification problem statement.
Updated after every change. Status: ✅ done · 🔧 in progress · ⬜ planned

## Roadmap

| # | Item | Status |
|---|------|--------|
| 1 | PWA foundation: service worker, offline page, install prompt, richer manifest, maskable icon | ✅ (code complete; needs device test) |
| 2 | In-app QR scanner on officer inspection page (+ GPS stamp) | ✅ (code complete; needs device test) |
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
- The `scripts/prerender.mjs` problem noted here was fixed afterwards, see "Follow-up: tests and prerender" below.

### 2026-10-14 — #2 In-app QR scanner + GPS stamp
**Added**
- `frontend/src/components/domain/QrScanner.tsx` — camera scanner (rear camera). Uses native `BarcodeDetector` when present, falls back to `jsqr` (iOS Safari/Firefox). Accepts a bare UIID or any URL containing one (`LM-YY-XXXXXXXX`); other QR codes are ignored with a hint. Camera stops on close/unmount; video never leaves the device.
- `frontend/src/lib/geo.ts` — `getGpsFix()` one-shot GPS helper; resolves `null` on denial/timeout, never blocks.
- Dependency: `jsqr@1.4.0`.

**Changed**
- `frontend/src/pages/officer/Inspection.tsx` — "Scan QR with camera" button under the UIID field; a scan fills the field and the existing match/confirm logic runs unchanged. Submission sends `identity_method` (`qr` | `manual`) and a GPS fix. Existing layout and steps untouched.
- `frontend/src/lib/types.ts`, `endpoints.ts` — new optional fields.
- `backend/app/models/inspection.py`, `routers/inspections.py` — `InspectionCreate` accepts `identity_method` (optional) and a required `location {lat, lng, accuracy_m}` (range-validated); both stored on the inspection and returned by `GET /inspections/{id}`. 

**Notes**
- Checked: `tsc -b` and `vite build` pass; pydantic validation tested (defaults, valid, out-of-range rejected); UIID extraction tested.
- Not tested on a real device. Camera and GPS need HTTPS (fine on Render/Vercel) and user permission.
- **GPS is mandatory** (follow-up). The page requests location on open; Pass/Fail stay disabled until a fix exists, with a status line and Retry button in step 4. `location` is a required field on `POST /inspections` (missing → 422). Breaking for any client not sending it; the bundled frontend does. Pre-existing inspections keep `location: null`.

### 2026-10-14 — Follow-up: tests and prerender
**Added**
- `backend/tests/test_inspections.py` — 19 tests for `POST/GET /inspections`: location mandatory (missing, null, out-of-range, wrong type → 422, nothing written), valid fix stored and returned, `identity_method` default/validation, accuracy optional, pass → certified + certificate job, fail → rejected, assigned-officer-only, status must be `scheduled`, bad ids, auth, and legacy records without location. Verified the tests fail when the requirement is removed. Full backend suite: 241 passed.

**Fixed — SEO prerender was never running**
- `frontend/index.html` — added the `<!-- seo:head -->` / `<!-- /seo:head -->` markers the script requires.
- `frontend/package.json` — `npm run build` is now `tsc -b && vite build && node scripts/prerender.mjs`. `npm run build:spa` keeps the old build without prerender.
- `frontend/src/context/AuthContext.tsx`, `entry-server.tsx` — `AuthProvider` takes an optional `initialStatus`; the prerender passes `"guest"`. Before, Landing rendered nothing at build time (it returns null while auth is "loading"), so `/` had no `<h1>` and the prerender failed. Browser behaviour is unchanged.
- `frontend/scripts/prerender.mjs` — if `VITE_SITE_URL` is unset it falls back to the host's public URL (`RENDER_EXTERNAL_URL` on Render, `VERCEL_PROJECT_PRODUCTION_URL` on Vercel) with a warning, so a deploy without the variable still builds. With neither: on Render/Vercel/CI the build fails with a clear message; on a plain local machine the prerender is skipped with a warning (dist/ stays a working SPA build, without sitemap/robots). `.env.example` documents the variable.
- `render.yaml` — new `VITE_SITE_URL` variable (set it to your real domain). The catch-all `/* → /index.html` rewrite is gone; replaced by explicit routes: `/app/*` and `/verify/*` → `app-shell.html` (noindex shell), public pages → their prerendered files. Unknown URLs now get `404.html` with a real 404.
- `frontend/vercel.json` — kept in sync (`cleanUrls`, same two rewrites, no catch-all).
- `.github/workflows/ci.yml` — frontend build sets a placeholder `VITE_SITE_URL`.
- `frontend/eslint.config.js` — service-worker globals for `public/sw.js`; `npm run lint` was failing with 18 errors from `sw.js` (from #1) and passes now. Also fixed one lint error in `QrScanner.tsx`.

**Notes**
- Checked with `scripts/preview-prod.mjs` (follows vercel.json): `/`, `/login`, `/verify` serve their own titles; `/verify/<id>` and `/app/*` serve the generic noindex shell; unknown URL → 404; sitemap and robots generated. Not tested on Render itself: after deploying, open `/`, `/verify`, `/login`, a deep `/app/owner/instruments`, and a nonsense URL.
- The frontend is actually hosted on Vercel, so `frontend/vercel.json` is the live routing config (the `render.yaml` frontend block is only for a Render deploy). Set `VITE_SITE_URL` in Vercel (Project → Settings → Environment Variables) before relying on canonical URLs/sitemap.
- The built pages replace themselves when the app boots (client uses `createRoot`, not hydration), so crawlers see full content and users get the normal app.
