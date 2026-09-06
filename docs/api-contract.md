# MaapSetu — API Contract (Backend Lead scope)

**Base URL:** `/api/v1`
**Auth:** JWT in `Authorization: Bearer <token>` header, unless marked **public**.
**Interactive docs:** run the server and open `/docs` for a live, clickable version of everything below.

Roles: `owner`, `lmo`, `gatc`, `admin`

Frontend display labels for these roles (login page / dashboard headers) — the API
itself only ever uses the short codes above, this mapping is frontend-only:

| Role code | Display label |
|---|---|
| `owner` | Business / User |
| `lmo` | Legal Metrology Officer |
| `gatc` | GATC |
| `admin` | Super Admin |

---

## Auth

### POST `/auth/register` — public
Register a new user.

**Body**
```json
{
  "name": "Rahul Sharma",
  "email": "rahul@example.com",
  "password": "secret123",
  "role": "owner",
  "org_type": null,
  "org_name": "Sharma General Store",
  "contact": "9876543210"
}
```
`org_type` is `"LMO"` or `"GATC"` — only relevant when `role` is `lmo` or `gatc`.

**Response** `201`
```json
{
  "user": { "id": "...", "name": "...", "email": "...", "role": "owner", "org_type": null, "org_name": "...", "contact": "..." },
  "token": "eyJhbGciOi..."
}
```

### POST `/auth/login` — public
**Body:** `{ "email": "...", "password": "..." }`
**Response:** same shape as register.

### GET `/auth/me`
Returns the currently authenticated user.
**Response:** `{ "user": {...} }`

---

## Instruments

### POST `/instruments` — role: `owner`
Register a new instrument.

**Body**
```json
{
  "type": "Electronic Weighing Machine",
  "manufacturer": "XYZ",
  "model": "ABC-200",
  "capacity": "30 kg",
  "serial_no": "123456",
  "location": "Baharampur, West Bengal"
}
```
`serial_no` must be unique across the whole system — a duplicate returns `409`.

**Response** `201`: the created instrument, plus `id` and `owner_id`.

### GET `/instruments`
Role-scoped:
- `owner` → only their own instruments
- `admin` → all instruments; optionally filter with `?owner_id=<id>`
- `lmo` / `gatc` → **403**, not authorized (officers reach instruments via their assigned applications instead)

### GET `/instruments/{instrument_id}`
Returns one instrument. Only its owner or an admin can view it.

---

## Applications

### POST `/applications` — role: `owner`
Submit a verification application for one of your own instruments.

**Body:** `{ "instrument_id": "..." }`
**Response** `201`: application with `status: "submitted"`.

### GET `/applications`
Role-scoped:
- `owner` → their own applications
- `lmo` / `gatc` → the unclaimed queue (`status=submitted`, unassigned) by default; pass `?mine=true` to see applications assigned to them instead
- `admin` → everything

Optional query param for all roles: `?status=<status>` to filter by status.

### GET `/applications/{application_id}`
Returns one application with its full status `history[]`. Visible to its owner, its assigned officer, or an admin.

### POST `/applications/{application_id}/claim` — role: `lmo`, `gatc`
Self-claim an unassigned application from the queue. Sets `assigned_officer_id` to the calling officer and transitions status `submitted → scheduled`.

Claiming is atomic — if two officers hit this at the same instant, exactly one succeeds. Returns `409` if the application is already claimed by someone else (whether that happened moments ago or simultaneously), `404` if the application doesn't exist.

---

## Inspections

### POST `/inspections` — role: `lmo`, `gatc`
Submit an inspection result for an application assigned to you.

**Body**
```json
{
  "application_id": "...",
  "observations": "Accurate to spec, no discrepancy found",
  "result": "pass",
  "photos": ["https://res.cloudinary.com/.../photo1.jpg"]
}
```
`result` is `"pass"` or `"fail"`. `photos` is a list of URLs — upload each photo first via `POST /uploads/photo` to get these URLs.

**Requirements:** the application must currently be `scheduled` and assigned to you, or this returns `409` / `403`.

**Effect:** automatically transitions the application `scheduled → inspected → certified` (if `pass`) or `→ rejected` (if `fail`). On a pass, a certificate is generated and stored (see Certificates below). If certificate generation fails (e.g. Cloudinary is down), the inspection still succeeds and the application stays `certified` — the certificate can be regenerated separately, this endpoint won't fail because of it.

### GET `/inspections/{inspection_id}`
Returns one inspection. Visible to the officer who submitted it, or an admin.

---

## Dashboards

Each role has its own dashboard endpoint — there is no shared/combined dashboard route.

### GET `/dashboard/owner` — role: `owner`
```json
{
  "total_instruments": 12,
  "verified": 9,
  "pending": 2,
  "expired": 1,
  "next_expiry": {
    "instrument_type": "Weighing Machine",
    "serial_no": "SN1",
    "valid_until": "2026-09-21T08:10:36+00:00",
    "days_remaining": 14
  }
}
```
`next_expiry` is `null` if there are no active certificates.

### GET `/dashboard/lmo` — role: `lmo`
### GET `/dashboard/gatc` — role: `gatc`
Same response shape for both — each officer only ever sees their own numbers, and an LMO account cannot call the GATC route or vice versa:
```json
{ "assigned": 45, "pending": 18, "completed": 27, "today_inspections": 6 }
```

### GET `/dashboard/admin` — role: `admin`
```json
{
  "total_instruments": 125430,
  "verified": 110210,
  "pending": 8420,
  "expired": 6800,
  "by_location": [
    { "location": "West Bengal", "count": 25430 },
    { "location": "Bihar", "count": 18200 }
  ]
}
```
⚠️ `by_location` groups on the free-text `location` field on Instrument, not a normalized state field — inconsistent input text will fragment the grouping. Ask Aritra/Anushka to add a dedicated `state` dropdown field on the registration form if a true state-wise breakdown is needed for the demo.

---

## Certificates

### GET `/certificates/verify/{cert_id}` — **public**, no auth
Powers verify-page's `[certId].jsx`. This is the locked response contract confirmed with Aritra/Anushka — don't change the shape without telling them.
```json
{
  "valid": true,
  "certificate": {
    "id": "...",
    "verified_on": "2026-08-05T13:00:00+00:00",
    "valid_until": "2027-08-05T13:00:00+00:00",
    "is_expired": false
  },
  "instrument": {
    "type": "Electronic Weighing Machine",
    "manufacturer": "Avery",
    "model": "AWS-200",
    "serial_no": "AWS200-2024-0001"
  },
  "owner": {
    "org_name": "Sharma General Store",
    "location": "Baharampur, West Bengal"
  }
}
```
If the certificate doesn't exist: `{ "valid": false, "reason": "not_found" }` (still `200`, not a `404` — this is a QR-scan landing page, not an API error case).

### GET `/certificates/{cert_id}`
Full certificate detail including `qr_url` and `pdf_url`. Access-controlled: visible to the certificate's owner (via the underlying application), the officer assigned to that application, or an admin — not to any other authenticated user.

### GET `/certificates/`
Lists certificates, scoped by role:
- `owner` → only certificates tied to their own applications
- `lmo` / `gatc` → only certificates tied to applications assigned to them
- `admin` → everything

---

## Uploads

### POST `/uploads/photo`
Multipart file upload (`file` field). Uploads to Cloudinary and returns the URL, for use in an Inspection's `photos[]`.
**Response:** `{ "url": "https://res.cloudinary.com/..." }`

---

## Application status lifecycle

```
submitted → scheduled → inspected → certified → expiring → expired
                              ↘ rejected
```
All transitions are enforced by `app/services/status_transition.py` — nothing outside that file should ever set `status` directly, including the expiry cron and certificate logic.

The expiry cron (`app/services/expiry_cron.py`) runs hourly and handles both ends automatically: certificates within 30 days of expiry move their application `certified → expiring` and log a reminder alert; certificates past `valid_until` move `expiring → expired` and log an expired alert.

---

## Seeding

`backend/seed/seed.py` wipes and reseeds all 6 collections from `backend/seed/seed_data.py`. Run with:
```
cd backend
python -m seed.seed
```
Seeded users share their `seed_data.py` passwords (e.g. `seed-pass-001`) — log in with the plaintext version, the DB only stores the hash.