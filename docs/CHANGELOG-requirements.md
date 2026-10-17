# Requirements Tracker & Change Log

Tracks the gap-closing work against the Legal Metrology e-verification problem statement.
Updated after every change. Status: ✅ done · 🔧 in progress · ⬜ planned

## Roadmap

| # | Item | Status |
|---|------|--------|
| 1 | PWA foundation: service worker, offline page, install prompt, richer manifest, maskable icon | ✅ (code complete; needs device test) |
| 2 | In-app QR scanner on officer inspection page (+ GPS stamp) | ✅ (code complete; needs device test) |
| 3 | Offline-capable inspection with background sync | ✅ (code complete; needs device test and a backend `pytest` run) |
| 4 | Re-verification flow (application type, link to previous certificate, Renew button) | ✅ (code complete; backend `pytest` and frontend build pass) |
| 5 | Real scheduling (admin/LMO allocation, date + slot, reschedule) | ✅ (backend `pytest` 322 passed; frontend lint and build pass; not tried in a browser) |
| 6 | Richer inspection form (per-instrument parameters, stamp/seal number) | ✅ (backend `pytest` 345 passed; frontend lint and build pass; not tried in a browser or on a device) |
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

### 2026-10-16 — #3 Offline-capable inspection with automatic sync
**Added**
- `frontend/src/lib/offlineQueue.ts` — IndexedDB queue (`maapsetu-offline` / `inspections`) for finished inspections that couldn't be sent. Stores the form, GPS fix, `captured_at`, already-uploaded photo URLs and photos taken offline (as blobs). Entries are tagged with the officer's user id.
- `frontend/src/lib/offlineSync.ts` — `syncQueue(userId)`: oldest first, one run at a time; uploads queued photos (progress saved per photo), then `POST /inspections`. Network/server trouble or sign-out → keep everything and retry later; a definite rejection (403/404/409/422…) → mark that item "failed" with a plain-language reason and continue.
- `frontend/src/hooks/useOfflineSync.ts` — `useOnlineStatus`, `useQueuedInspections`, and the sync engine hook. Syncs on app open, on reconnect, on tab refocus and every 60 s while items wait; refreshes applications/dashboard data after a send.
- `frontend/src/components/ui/OfflineSyncBanner.tsx` — officer-only strip in `AppShell`: offline notice, "N inspections saved on this device" with **Send now**, and rejected items with **Discard**.
- Backend: `client_id` (idempotency key) and `captured_at` on `InspectionCreate`; `submitted_offline` on the response; partial unique index on `inspections(officer_id, client_id)` in `init_indexes`.

**Changed**
- `frontend/src/pages/officer/Inspection.tsx` — generates one `client_id` per inspection and sends it with `captured_at`; if offline, or the connection drops mid-submit, saves to the queue and shows "Saved on this device" (also shown if this application is already queued). A failed background refetch no longer replaces the loaded form with an error.
- `frontend/src/components/domain/PhotoUploader.tsx` — optional `pending` / `onPendingChange`: a photo whose upload fails for lack of connection is kept (labelled "Saved offline") instead of being lost.
- `backend/app/routers/inspections.py` — replaying the same `(officer, client_id)` returns the original with `200` before any status check, so no second transition, email or certificate; a concurrent duplicate is caught by the unique index. `captured_at` becomes `inspected_at` only if not in the future (5 min skew) and not older than 14 days, else server time; `received_at` is always stored.
- `README.md` — new Offline Inspections section; features, stack, project structure, API table, testing and roadmap now cover the PWA, QR scanner, GPS stamp and offline sync. `docs/api-contract.md` — documents `location`, `identity_method`, `client_id`, `captured_at`, `submitted_offline`.
- `backend/tests/test_inspections.py` — 9 new tests: replay returns the original and applies once, no `client_id` still 409s, `client_id` is per officer, invalid ids → 422, `captured_at` used and flagged offline, future/too-old `captured_at` falls back to server time.

**Notes**
- **Not run:** the authoring environment had no access to the npm/PyPI registries, so `npm run build`/`lint` and `pytest` were not run. Checked instead: the two new library files type-check (`tsc --strict`), all edited Python files parse, and the `captured_at` rule was exercised on its own. Run `cd backend && pytest tests/test_inspections.py` and `cd frontend && npm ci && npm run lint && npm run build` before merging.
- Test on a phone: open an inspection, switch to airplane mode, take photos, submit (expect "Saved on this device"), switch back and watch the banner clear and the application become certified/rejected.
- Known limits: sync runs while the app is open (no service-worker background sync — iOS lacks it and the access token lives in page storage); a page *reloaded* offline shows `offline.html`, so the inspection must be opened while online first; signing out leaves the queue on the device until the same officer signs in again.
- Free-text observations and photos wait in the browser profile until sent. On a shared device, sign out only after the queue is empty.

### 2026-10-17 — Infra: email/certificate queue now always has a worker
**Problem:** with `REDIS_URL` set and no process running `run_worker.py` (Render's free plan has no Background Workers), queued jobs waited in Redis forever. Officer-credential and password-reset emails reported "sent" but never went out. Failed sends were also reported as successful jobs, so nothing retried.

**Added**
- `backend/app/services/embedded_worker.py` — an RQ worker thread inside each web process. Every instance/uvicorn worker consumes the same Redis queue, so jobs are spread across instances and each runs once (load balancing). Auto-restarts if Redis drops. `EMBEDDED_WORKER=false` disables it when a dedicated worker is deployed; `EMBEDDED_WORKER_THREADS` (default 1) sets threads per process.
- `backend/tests/test_email_queue.py` — tests for the points below.

**Changed**
- `backend/app/services/jobs.py` — email jobs now raise `MailSendError` when the provider rejects a send, so RQ retries and records the failure; new `enqueue_email()` retries at 10 s, 1 min and 5 min; `_worker_available()` result cached for 5 s so request paths don't hit Redis every time.
- `backend/app/routers/admin_users.py` — officer-created and password-reset emails use `enqueue_email()`.
- `backend/app/main.py` — starts/stops the embedded worker; `/api/v1/health` also reports `embedded_worker`.
- `backend/run_worker.py` — uses the standard forking `Worker` (enforced job timeouts) on Linux; the no-fork worker only on Windows.
- `render.yaml` — added `REDIS_URL`, `BREVO_API_KEY`, `SMTP_USE_TLS`, `EMBEDDED_WORKER`, plus a commented dedicated worker service for paid plans.
- Caching is untouched (frontend asset caching, service worker rules, Mongo read preferences, Redis-backed rate limits).

**Notes**
- Needs a backend deploy; Auto-Deploy is off on the Render service, so use Manual Deploy.
- Not run here (no network for `pip install`): run `pytest backend/tests/test_email_queue.py` locally.
- Free-plan caveat: Render sleeps idle free services, so queued retries pause while asleep and resume on the next request.

### 2026-10-17 — Fix: Brevo 400 "valid sender email required"
- `backend/app/config/settings.py` — `SMTP_FROM` / `NOREPLY_FROM` now tolerate whitespace/newlines and a value wrapped in quotes (common dashboard paste mistakes).
- `backend/app/services/mailer.py` — the sender is validated before calling Brevo; a bad value logs which setting is wrong instead of a bare 400. An invalid `NOREPLY_FROM` falls back to `SMTP_FROM`. Brevo rejections now log the sender used.
- `backend/app/main.py` — the startup "Email config" line also shows the `from` and `noreply` addresses.

### 2026-10-17 — Fix: public verify page rejected the printed certificate number
- `backend/app/routers/certificates.py` — `GET /certificates/verify/{id}` matched only the internal certificate id (what the QR code carries), so typing the printed `CERT-YYYYMMDD-XXXXXX` always gave "Not found". It now matches the id first, then `cert_no` (trimmed, case-insensitive), and returns `cert_no`.
- `frontend/src/pages/public/VerifyCertificate.tsx`, `lib/types.ts` — the "Certificate ID" row shows the printed number.
- `backend/tests/test_certificate_pipeline.py` — lookup by id, by number, by lower-case number, and not-found.

### 2026-10-17 — #4 Re-verification flow
**Added**
- `application_type` (`initial` | `renewal`), `previous_certificate_id` and `previous_cert_no` on applications. The **server** decides the type: an instrument that already has a certificate is a renewal. `POST /applications` takes an optional `previous_certificate_id`; without it the instrument's newest certificate is linked, so the emailed "Renew now" links (`/applications/new?instrument=…`) and old clients work unchanged. A certificate id that doesn't belong to the instrument → 422.
- One open application per instrument: a new application while one is `submitted`, `scheduled` or `inspected` → 409 with a plain message. Finished ones (`certified`, `rejected`, `expiring`, `expired`) don't block.
- The link is copied onto the new certificate (`application_type`, `previous_certificate_id`, `previous_cert_no`), returned by the certificate API (together with `instrument_id`), and printed on the PDF as a "Re-verification of" row.
- Indexes: `applications(instrument_id, status)`, `certificates(instrument_id, valid_until)`.
- Frontend: **Renew certificate** button on the owner's certificate page (newest certificate of an instrument only; disabled as "Renewal in progress" while an application is open), opening the existing application form with the instrument preselected and a one-line "Re-verification of CERT-…" note. A "Re-verification" badge and "Renews certificate …" line on the application page (owner and officer views), a "Renewal" badge in application lists, and a "Re-verification of" field on the certificate page. No layout changes.
- `backend/tests/test_reverification.py` — tests for type/linking, one open application, the window, queue order, chained validity and the verify-page block.

**Notes**
- Existing records are treated as `initial`; no migration needed.
- **Renewal window + chained validity + "in progress" status** (decided after the first pass, replaces an interim "only after expiry" rule):
  - Re-verification opens `REVERIFY_WINDOW_DAYS` (default 30, `0` = only after expiry) before the newest certificate expires and stays open afterwards. Earlier → 409 "valid until …, you can apply from <date>". The Renew button is disabled before that and reads "Renewable from <date>"; the date comes from the certificate API (`renewal_opens_on`).
  - **Chained validity:** a certificate issued while the old one is still in force starts on the old expiry date (`valid_from`) and runs one year from there, so no days are lost; issued after expiry it starts on the issue date. The PDF and certificate pages show "Valid from" only when it starts later than the issue date.
  - **Public verify page:** an expired certificate whose instrument has an application in progress shows "Re-verification in progress — the owner applied on … (status: …)". This block is computed live and is not cached; the response never exposes the internal instrument id.
  - **Officer queue:** renewals come first, most urgent expiry at the top (already-expired ahead of soon-to-expire), then first-time applications newest first. Lists show "Expires in Nd" / "Expired Nd ago" badges (`previous_valid_until` is stored on the application).
  - Owner dashboard "Upcoming renewal" skips a certificate that has already been renewed.
  - Not done yet (belongs to #5/#8): a target time for officers to inspect, and treating "applied, pending" as a mitigating status in the enforcement module. The verify-page block is the data hook for it.
- A renewal issues a new certificate; the old one stays valid until its own expiry date, and the expiry reminders already stop for it once a newer certificate exists.
- Checked: backend `pytest tests` 278 passed; frontend `tsc -b`, `eslint` and `npm run build` pass. Not tried in a browser.

### 2026-10-17 — #5 Real scheduling (verified in code) + lint fix
**Checked in the codebase — what #5 consists of**
- `backend/app/services/scheduling.py` — one place for the rules: two slots a day (Morning 10:00-13:00, Afternoon 14:00-17:00 IST), Sundays off, no past dates, at most `SCHEDULE_MAX_AHEAD_DAYS` (60) ahead, `SLOT_CAPACITY_PER_OFFICER` (4) per officer per slot. Settings `SLOT_CAPACITY_PER_OFFICER`, `SCHEDULE_MIN_LEAD_DAYS`, `SCHEDULE_MAX_AHEAD_DAYS` are in `settings.py` and `render.yaml`.
- `backend/app/routers/applications.py` — `POST /applications/{id}/claim` now books a date and slot; `POST /applications/{id}/schedule` reschedules (assigned officer or admin, only while `scheduled`); `POST /applications/{id}/assign` lets an admin allocate a `submitted` application to a named officer or move a `scheduled` one to another officer (active account, inside jurisdiction); `GET /applications/slots` returns places left per date and slot (officers see only their own diary). A second capacity check after the write undoes the booking if two requests race for the last place. Every change is appended to `schedule_history`.
- Emails: `application_scheduled` and `inspection_rescheduled` (new and old slot, reason) in `email_templates.py` / `owner_notifications.py`.
- Frontend: `SchedulePicker` (officer and admin application pages), `ScheduleCard` (shown to everyone), `AddToCalendar` with `lib/calendar.ts` (Google Calendar link and `.ics` download, no account linking), `lib/schedule.ts` (mirrors the backend slots).
- Docs: `README.md` and `docs/api-contract.md` already describe the endpoints, rules and `schedule_history`.
- Tests: `backend/tests/test_scheduling.py` covers claim, bad date/slot, capacity per officer, jurisdiction, race for the last place, reschedule and history, admin assign/reassign, availability and the emails.

**Fixed — `npm run lint` failed with 8 `no-undef` errors in `frontend/src/lib/calendar.js`**
- Cause: compiled output (`calendar.js`, `schedule.js`, `types.js`) had been emitted next to `calendar.ts`, `schedule.ts` and `types.ts`. ESLint only gives browser globals to `.ts/.tsx` files, so it flagged `URLSearchParams`, `TextEncoder`, `Blob`, `URL`, `document` and `setTimeout` in the stray `.js` copy. Those copies were also a risk beyond lint: Vite tries `.js` before `.ts`, so a stale copy could shadow the real source.
- Removed the three stray `.js` files.
- `frontend/eslint.config.js` — ignores `src/**/*.js` (src is TypeScript only).
- `frontend/.gitignore` — ignores `src/**/*.js` and `*.tsbuildinfo` so a stray `tsc` emit can't be committed again.

**Notes**
- Run here: `npm ci && npm run lint` (clean) and `npm run build:spa` (passes, and no `.js` reappears in `src/`); backend `pytest tests` 322 passed (was 278 at #4).
- Not tried in a browser or on a device. Suggested check: claim an application with a date and slot, reschedule it, assign one from the admin page, and use both Add to calendar options.
- If this reappears: someone ran `tsc` without `--noEmit` (for example `npx tsc` from `frontend/`). Use `npm run build`, which already uses `tsc -b` with `noEmit`.

### 2026-10-17 — #6 Richer inspection form (per-instrument readings and checks, seal number)
**What an officer now records**
- **Test readings** — reference standard vs what the instrument showed, at least N per instrument type (3 loads for scales and weighbridges, 2 deliveries for a fuel dispenser, 1 for weights, and so on). The server works out `error` and `error_pct`; it deliberately does **not** judge them against a permitted limit, because limits depend on each instrument's class and rules and are not in this codebase. The officer decides Pass/Fail; the numbers are the evidence.
- **Checks** — yes/no items per type (zero reading, display, leaks, tamper signs, markings…). A Pass needs every check answered and every *required* one "Yes".
- **Seal / stamp number** — required for a Pass, not allowed on a Fail, normalised (trim, upper-case, 3-32 chars) and **unique** (partial unique index `inspections.seal_number`; reuse → 409, including the race between two officers).

**Added**
- `backend/app/config/inspection_forms.py` — the form for each of the 18 instrument types (units come from `instrument_specs.py`; a test fails if a new type has no form). `backend/app/services/inspection_form.py` — validation and the stored shape.
- Endpoints: `GET /inspections/form-spec?type=`, `GET /inspections/by-application/{id}` (officer/admin full; the owner gets result, readings, checks, seal and notes without `officer_id` or GPS).
- `frontend/src/components/domain/InspectionRecord.tsx` — "Inspection record" on the application page for owner, officer and admin (readings table with error, checks, seal, notes).
- Tests: 23 new (`test_inspections.py`, `test_certificate_pipeline.py`) — every type has a form, form-spec access, stored error values and zero reference, missing/bad/duplicate seal, too few readings, unanswered or unmet required check, unknown check, out-of-range readings, Fail rules, per-type forms, strict vs non-strict, replay of a queued inspection, owner redaction, seal on certificate / verify page / PDF.

**Changed**
- `POST /inspections` — new optional `test_points`, `checks`, `seal_number`; the response and `GET /inspections/{id}` return them plus a `form` snapshot (labels are stored with the record, so old records read the same if wording changes later). Idempotent replay by `client_id` is still checked first.
- Certificates — `seal_number` is copied onto the certificate, printed on the PDF ("Seal / Stamp No.", omitted for older certificates), returned by the certificate API and the public verify endpoint, and shown on the verify page and the certificate page so anyone can compare it with the seal on the instrument.
- `frontend/src/pages/officer/Inspection.tsx` — steps 3 (test readings with live error) and 4 (checks) added, seal number in the result step; the Pass button lists what is still missing. Drafts and the offline queue (`offlineDrafts.ts`, `offlineQueue.ts`, `offlineSync.ts`) carry the new fields; the form for an instrument type is kept in `localStorage` after the first load so the page still opens if the signal drops. If it can't be loaded at all, a Fail with notes is still possible and a Pass is not.
- `backend/app/config/settings.py`, `render.yaml`, `README.md`, `docs/api-contract.md` — new `INSPECTION_FORM_STRICT` (default `true`) and the endpoint/field docs.

**Notes**
- **Breaking for older clients:** with the default `INSPECTION_FORM_STRICT=true`, a Pass without the new fields is a 422. The bundled frontend sends them. An inspection queued on a phone **before** this deploy is rejected on sync with a plain message ("saved before the new form… discard and record it again"). To let those through temporarily, set `INSPECTION_FORM_STRICT=false` on the backend, then turn it back on.
- The partial unique index on `seal_number` is created at startup; if duplicate seal numbers ever existed it logs a warning instead of failing.
- The "what to test" lists (test counts, check wording) are sensible field defaults, not statutory text. Have a Legal Metrology officer review `inspection_forms.py` before real use; it is the only file to edit.
- Checked here: backend `pytest` 345 passed (was 322), `ruff check` clean; frontend `tsc -b`, `eslint .`, `npm run build` pass. Not tried in a browser or on a phone. Suggested check: open an inspection, fill readings and checks, try Pass without a seal (blocked), pass with one, open the application as the owner, then re-use the seal number on another inspection (expect the 409 message).

