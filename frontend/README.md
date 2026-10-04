# MaapSetu — Frontend

Frontend for the Legal Metrology verification platform (SIH 2026, PS 26036), built against
the real backend API contract (`/api/v1`, JWT auth, roles `owner` / `lmo` / `gatc` / `admin`).

## Stack

React 18 + TypeScript + Vite + Tailwind CSS, React Router, TanStack Query for server state,
a small typed fetch client (`src/lib/api.ts`) instead of a heavier HTTP library.

## Setup

```bash
cd frontend
npm install
cp .env.example .env      # point VITE_API_BASE_URL at your running backend
npm run dev
```

The backend's seed script (`backend/seed/seed.py`) gives you working logins for all four
roles — the passwords are in `backend/seed/seed_data.py`.

## Architecture

```
src/
  lib/          typed API client, endpoint functions, domain types, nav config
  hooks/        React Query hooks — the only things pages/components call
  context/      auth session state (JWT in localStorage, /auth/me on load)
  routes/       ProtectedRoute (auth + role gating)
  components/
    ui/         design-system primitives (Button, fields, StatusBadge, DataTable, states…)
    layout/     AppShell (nav rail / topbar / mobile bottom nav), PageHeader
    domain/     shared feature pieces used across roles (ApplicationOverview,
                LifecycleTimeline, PhotoUploader, Certificate views, tables)
  pages/
    auth/       login, register
    public/     /verify — the QR-scan landing page (no auth)
    owner/      business/user dashboard, instruments, applications, certificates
    officer/    shared LMO + GATC screens (queue, assignments, inspection workflow)
    admin/      system-wide views
```

One shell, one nav config, one component library — the four roles are different
views over the same lifecycle, not four separate apps (see `src/lib/nav.ts`).

## What this does and doesn't cover

Built to match the documented API exactly. Where the original product brief asked for
something the backend doesn't yet expose an endpoint for, it's **not** faked with mock
data — the API layer is structured so it drops in cleanly once the route exists:

- **No scheduling/calendar UI** — there's no `/schedule` endpoint; the lifecycle is
  `submitted → scheduled` via `/applications/{id}/claim`, which is what's built.
- **No notifications panel, no audit log viewer, no user/GATC/LMO management screens** —
  no corresponding endpoints in the contract.
- **No offline mode for field verification** — no sync strategy exists in the backend, so
  building one would just be UI theater. The inspection form is mobile-first instead.
- **QR scanning** is manual-entry only (`/verify/:certId` accepts a pasted or scanned-in ID).
  Wiring an actual camera scanner (e.g. a barcode-detection library) is a small addition
  once you confirm what's acceptable to add as a dependency.
- **Admin's location chart** groups on the instrument's free-text `location` field, per the
  contract's own caveat — it'll fragment on inconsistent input until a normalized `state`
  field exists.

## Design system

Palette, type (Source Serif 4 for display / Inter for UI), spacing, and status-color tokens
live in `tailwind.config.js`. Every lifecycle status renders through
`src/components/ui/StatusBadge.tsx` — that's the one place status → color mapping is
defined, so it can't drift between a table, a timeline, and a dashboard stat.

## Local development against the deployed (Render) API

Run the UI on your machine and talk to the API that is already running on Render. The API only allows
its deployed frontend origin in CORS, so the dev server proxies `/api` and `/ws` instead of calling it directly.

Create `frontend/.env.local` (git-ignored, overrides `.env`):

```
VITE_API_BASE_URL=
DEV_API_PROXY=https://<your-api>.onrender.com
```

Then `npm run dev` and open http://localhost:5173. `VITE_API_BASE_URL` must be **empty** (not `http://localhost:8000`),
otherwise the browser skips the proxy and hits CORS. Notes: the Render free plan sleeps, so the first request can take
up to a minute; this is the **live database**, so use test accounts, and remember status emails really are sent.

### Checking the production build locally (SEO output, routing, 404)

```
VITE_SITE_URL=https://example.com npm run build     # any valid https origin is fine for a local check
PREVIEW_API_PROXY=https://<your-api>.onrender.com npm run preview:prod
```

`preview:prod` serves `dist/` following `vercel.json` (clean URLs, rewrites, noindex headers, real 404) on
http://localhost:4173. Plain `vite preview` is not suitable for this: it answers every unknown URL with `index.html`.

## SEO

Everything SEO-related is driven by one file, `src/seo/seoConfig.ts` (per-route title, description,
indexable flag, sitemap hints, JSON-LD). `<Seo route="…" />` applies it on the client; `scripts/prerender.mjs`
(run by `npm run build` after `vite build`) uses the same config to emit static HTML, `sitemap.xml`,
`robots.txt` and `404.html` into `dist/`.

- **Env:** `VITE_SITE_URL` (required for production builds: https origin, no trailing slash, not localhost; a custom
  domain is strongly recommended), optional `VITE_GSC_VERIFICATION`. See `.env.example`.
- **Indexed:** `/`, `/verify`, `/register`, `/how-it-works`, `/about`. **noindex:** `/login`, `/pending`,
  `/change-password`, `/unauthorized`, `/verify/:certId`, `/app/**`, and the 404 page.
- **Adding a public page:** add an entry to `SEO_ROUTES` and `PRERENDER_ROUTES`, add the `<Route>` in `App.tsx`,
  render `<Seo route="/your-path" />` and exactly one `<h1>`. The build fails on titles over 60 characters,
  descriptions outside 120-160, duplicates, or a prerendered page without a single `<h1>`.
- **Hosting:** `vercel.json` rewrites only known client routes to `app-shell.html`; anything else gets the real
  404 from `404.html`.
  On Render, mirror the same rules in `render.yaml` (`routes` + `headers`) and set `VITE_SITE_URL` there;
  never add a `/* -> /index.html` catch-all, it defeats the prerendered pages and the real 404. Bump `lastmod` in `seoConfig.ts` when a page's content changes meaningfully.
- **Icons / OG image:** `public/` files are committed; regenerate with `scripts/generate-assets.mjs`.
