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
### GET `/auth/me`
Returns the currently authenticated user.
**Response:** the `UserOut` object representing the current user (returned directly, not wrapped):
```json
{ "id": "...", "name": "...", "email": "...", "role": "owner", "org_type": null, "org_name": "...", "contact": "..." }
```
Register a new user.

### GET `/instruments/{instrument_id}`
Returns one instrument. Only its owner or an admin can view it.
`serial_no` must be unique across the whole system — a duplicate returns `409`.
### GET `/instruments/by-uiid/{uiid}` — role: `lmo`, `gatc`, `admin`
Lookup an instrument by its `uiid` (used by officers after scanning a QR code).

**Response:** same as the single-instrument response; the returned object contains the `uiid` field (used by the frontend to match physical serial numbers).
```json
{
### GET `/certificates/verify/{cert_id}` — **public**, no auth
Powers verify-page's `[certId].jsx`. This is the locked response contract confirmed with Aritra/Anushka — don't change the shape without telling them.
  "instrument": {
    "type": "Electronic Weighing Machine",
    "manufacturer": "Avery",
    "model": "AWS-200",
    "uiid": "UIID-2024-0001"
  },
  "owner": {
    "org_name": "Sharma General Store",
    "location": "Baharampur, West Bengal"
  }

**Response** `201`
### GET `/certificates/`
Lists certificates. (Note: the current implementation returns certificates from the collection without role-based filtering server-side; frontend currently expects role-scoped results.)
- `owner` → frontend expects only their own certificates (not enforced server-side)
- `lmo` / `gatc` → frontend expects only certificates for assigned applications (not enforced server-side)
- `admin` → expects everything (this is effectively what the endpoint currently returns)
  "token": "eyJhbGciOi..."
}
```

### POST `/auth/login` — public
**Body:** `{ "email": "...", "password": "...", "remember_me": false }` — `remember_me` is optional and defaults to `false`.
**Response — owner accounts:** same shape as register, plus `"remember_me": true|false` — whether "remember me" was actually applied.
**Response — officer (`lmo`/`gatc`) and `admin` accounts:** the password is only step one. Nothing that grants access is released — no `token`, no refresh cookie, no `user`:
```json
{ "user": null, "token": null, "mfa_required": true,  "mfa_setup_required": false, "mfa_token": "<10-minute step token>" }
{ "user": null, "token": null, "mfa_required": false, "mfa_setup_required": true,  "mfa_token": "<10-minute step token>" }
```
`mfa_required` → call `/auth/mfa/verify`; `mfa_setup_required` (no authenticator yet) → `/auth/mfa/setup` then `/auth/mfa/confirm-setup`. See **Two-step verification** below. The failed-attempt counter is not cleared by the password step, only by a completed second step.
`remember_me: false` → the refresh cookie is a browser-session cookie (gone when the browser closes).
`remember_me: true` → the refresh cookie persists for `REMEMBER_ME_REFRESH_TOKEN_EXPIRES_DAYS` (default 30), restarting on every `/auth/refresh`.
**Owner accounts only:** for `lmo`, `gatc` and `admin` the flag is ignored — they always get a session cookie and the response reports `"remember_me": false`. `/auth/refresh` returns the same `remember_me` field.

### Two-step verification — officer and admin accounts
TOTP (RFC 6238: SHA-1, 6 digits, 30-second steps, ±1 step of clock drift) — compatible with Google/Microsoft Authenticator, Authy, etc. These three endpoints are **public** (no Bearer token); they authenticate with the `mfa_token` from `/auth/login`. The `mfa_token` is a JWT of type `mfa` bound to one step (`setup` or `verify`): it is rejected as a Bearer token everywhere else, rejected for the wrong step, expires after `MFA_TOKEN_EXPIRES_MINUTES`, and stops working if the account's password changes or its sessions are revoked. Every failure returns `401` (`429` when locked, `400` for a stale/duplicate setup) and all share the login lockout counter. All three share the `/login` per-IP rate limit.

#### POST `/auth/mfa/setup`
**Body:** `{ "mfa_token": "..." }` (step `setup`) → `{ "secret": "BASE32…", "otpauth_uri": "otpauth://totp/…", "qr_data_uri": "data:image/png;base64,…" }`. Repeating the call within 15 minutes returns the **same** secret, so a double-click or reload can't desynchronise the app and the server. `400` if two-step verification is already on.

#### POST `/auth/mfa/confirm-setup`
**Body:** `{ "mfa_token": "...", "code": "123456" }` (step `setup`). The code proves the authenticator was scanned correctly. On success two-step verification is turned on and the **session starts**: `LoginResponse` with `user`, `token`, the refresh cookie, and `"recovery_codes": [8 one-time codes]` — **shown only in this response**. `401` wrong code; `400` setup missing/expired (15 min).

#### POST `/auth/mfa/verify`
**Body:** `{ "mfa_token": "...", "code": "123456" }` (step `verify`). `code` is the 6-digit authenticator code **or** a recovery code (`k7m2x-q9d4p`; case, dashes and spaces are ignored). On success the session starts (`user`, `token`, refresh cookie; never "remember me"). A TOTP time-step can be used once (an accepted step is refused again even inside its 30-second window); each recovery code works once, and the response then carries `"recovery_codes_remaining": N`. `401` invalid code; `429` locked out; `503` the stored secret can't be decrypted (encryption key changed — contact an administrator).

**Sessions and two-step.** Refresh tokens issued after the second step carry a `mfa_verified` mark, which `/auth/refresh` **requires** for officer/admin accounts (`401 "Please sign in again."` otherwise) — a session can never be renewed from a password alone, and refresh tokens issued before this feature existed are retired. `/auth/refresh` also refuses accounts whose status is no longer `active`. `/auth/change-password` preserves the mark on the replacement session.

**Resetting it.** An admin resets an officer's with `POST /admin/users/{id}/reset-mfa` (below). The admin account's own is reset by the operator with `python reset_mfa.py <email>` — deliberately not exposed through the API.

### Password policy (register, change-password, reset-password)
8–64 characters, with at least one uppercase letter, one lowercase letter, one digit and one special character (anything that isn't a letter or digit), and not on a short list of very common passwords. Violations return `422` with a message naming what's missing. The policy is **not** applied at login, so older accounts can still sign in.

### POST `/auth/change-password` — authenticated
**Body:** `{ "current_password": "...", "new_password": "..." }`
**Response:** the updated `UserOut` **plus** `"token"` (a fresh access token) and `"remember_me"`; a fresh refresh cookie is set, exactly like login.
`401` wrong current password; `400` new password identical to the current one; `422` new password breaks the policy.
**Signs out every other session.** A successful change bumps `token_version` (all access tokens issued so far die) and revokes every refresh token for the account — other browsers, other devices, and anyone holding the old password or a stolen session are signed out. The device that made the change is not: it receives the replacement `token` and refresh cookie in this response and must use them (the token it sent is no longer valid). The new session keeps the old one's "remember me" choice (owners only). A "your password was changed" email is sent and the event is audit-logged.

### POST `/auth/forgot-password` — public
**Body:** `{ "email": "..." }`
Emails a 6-digit reset code (valid 10 minutes) if a **business/owner** account exists for the email. **Always** returns `200 { "sent": true }` — whether or not the account exists and whether or not it is an officer/admin account (those never receive a code) — so it can't be used to discover accounts or roles. At most one email per account per `PASSWORD_RESET_COOLDOWN_SECONDS` (default 60); rate-limited per IP like `/login`.

### POST `/auth/reset-password` — public
**Body:** `{ "email": "...", "code": "123456", "new_password": "..." }`
**Response:** `{ "reset": true }`. Wrong, expired, already-used, over-attempted (5 tries) and unknown-email cases all return the same `400 "Invalid or expired code. Please request a new one."`.
Officer (`lmo`/`gatc`) and `admin` accounts always get this same `400`, even with a valid code.
On success: every existing session is signed out (access tokens via `token_version`, all refresh tokens revoked), any failed-login lockout is cleared, and a "your password was changed" email is sent.

### POST `/admin/users/{user_id}/reset-password` — role: `admin`
The only way an `lmo`/`gatc` officer's password gets reset (they can't self-serve).
**Response:** `OfficerCreatedOut` — `{ "user": {...}, "temp_password": "...", "emailed": true|false }`. The temporary password is shown once and also emailed; the officer must set a new one at next login (`must_change_password: true`). All of the officer's sessions are revoked, any lockout is cleared, and pending reset codes are deleted.
`400` invalid id, or target is an `owner`/`admin`; `404` no such user; `403` caller isn't an admin. The `admin` account itself is recovered by the operator re-running `seed_super_admin.py`.

### POST `/admin/users/{user_id}/reset-mfa` — role: `admin`
Clears an officer's two-step verification (lost phone, no recovery codes left). **Response:** the officer's `UserOut` with `"mfa_enabled": false`. The officer's secret, recovery codes and sessions are all revoked; at their next sign-in they are asked to enrol a new authenticator. `400` invalid id, or the target is an `owner`/`admin`; `404` no such user; `403` caller isn't an admin.

### Admin officer management — changes
- `POST /admin/users/{id}/reject` ("suspend") now also **ends the officer's sessions immediately** (token_version bump + all refresh tokens revoked). Previously it only blocked new sign-ins. `POST /admin/users/{id}/approve` reactivates.
- `GET /admin/users` / `/admin/users/pending` and every `UserOut` now include `"mfa_enabled": true|false`.

### POST `/otp/send` — public (signup email verification)
**Body:** `{ "channel": "email", "identifier": "user@example.com" }` → `200 { "sent": true }` (the email is sent in the background). Two limits, so it can't be used to spam an inbox the caller doesn't own:
- per IP: 5 requests / 15 minutes (`429` from the rate limiter);
- per address: one code per `OTP_SEND_COOLDOWN_SECONDS` (default 60) — a second request inside that window returns `429 { "detail": "A code was just sent. Please wait 60 seconds before requesting another." }` with a `Retry-After` header. The cooldown applies to every address equally (whether or not it has an account), so it reveals nothing about who is registered.
`POST /otp/verify` is limited to 15 requests / 15 minutes per IP (and 5 wrong guesses burn a code).

### GET `/admin/audit-logs` — role: `admin`
Read-only view of the audit log (below). There is deliberately no endpoint that edits or deletes a record; records leave the system only when MongoDB expires them after `AUDIT_LOG_RETENTION_DAYS`. Newest first. All filters are optional and combine with AND.

| Query parameter | Meaning |
|---|---|
| `event` | exact event name — must be one of the names in `events` (else `400`) |
| `outcome` | `success` · `failure` · `blocked` · `ignored` |
| `role` | `owner` · `lmo` · `gatc` · `admin` — the role of the account the event is about |
| `search` | text contained in the account's **or** the acting admin's email, case-insensitive, matched literally (not as a pattern); max 100 chars |
| `date_from`, `date_to` | `YYYY-MM-DD` (UTC), both days inclusive; `date_from` after `date_to` → `400` |
| `page` (default 1, max 1000), `page_size` (default 50, max 100) | pagination |

**Response:** `{ "items": [ { "id", "event", "outcome", "email", "user_id", "role", "actor_id", "actor_email", "ip", "user_agent", "detail", "created_at" } ], "total", "page", "page_size", "events": [every event name] }`. `created_at` is an ISO 8601 UTC timestamp. `403` for non-admins. When `MONGO_READ_PREFERENCE=secondaryPreferred` this reads from a replica-set secondary (it may trail the newest events by a moment).

### Audit log
Security events are written to the `audit_logs` collection (retained `AUDIT_LOG_RETENTION_DAYS`, default 365, minimum 180) and to the `app.audit` log stream. Admin-initiated events also store `actor_email`, so the history stays readable if that account later changes. Records hold the event, outcome (`success` / `failure` / `blocked` / `ignored`), account email / id / role, acting admin (if any), client IP, user agent and a short reason — never passwords, reset codes or tokens. Writing a record is best-effort: a logging failure never fails the request.

| Event | Outcomes / `detail` values |
|---|---|
| `signup_otp_requested` | `success` (`code_sent`), `ignored` (`cooldown`) — signup verification emails, so mail-bombing attempts are visible |
| `login_success` | `success`; `detail`: `remember_me` (long-lived session granted), `mfa_totp`, `mfa_recovery_code` or `mfa_setup` (officer/admin sign-ins, by how the second step was passed) |
| `login_failed` | `failure`; `unknown_email`, `wrong_password`, `wrong_password_account_locked` (this attempt triggered the lockout) |
| `login_blocked` | `blocked`; `account_locked`, `account_pending`, `account_rejected` |
| `login_password_verified` | `success`; `mfa_required` or `mfa_setup_required` — officer/admin password accepted, second step pending (no session yet) |
| `mfa_setup_started` / `mfa_enabled` | `success` — authenticator enrolment began / was confirmed |
| `mfa_failed` | `failure`; `wrong_code`, `replayed_code`, `setup_wrong_code` (each also `…_account_locked` when it triggered the lockout), `secret_undecryptable` |
| `mfa_blocked` | `blocked`; `account_locked` |
| `mfa_reset` | `success`; `actor_id` is the admin, or `operator-script` for `reset_mfa.py` |
| `account_registered` | `success` (`auto_login`) — owner self-registration |
| `account_registration_failed` | `failure` (`email_not_verified`, `email_exists`, `invalid_role`), `blocked` (`role_not_allowed:<role>` — someone tried to self-register as an officer/admin) |
| `officer_created` | `success`; `actor_id` = admin, `detail: jurisdiction=<state>/<district or *>` |
| `officer_creation_failed` | `failure`; `email_exists`, `unknown_state`, `unknown_district`, `invalid_role` |
| `account_approved` / `account_suspended` | `success`; `actor_id` = admin, `detail: from=<previous status>` (`/approve` and `/reject`) |
| `logout` / `logout_all` | `success` (`logout` is only recorded when the cookie maps to a real session) |
| `refresh_rejected` | `blocked`; `revoked_token_presented` (an already-used refresh token was shown again — a stale tab racing a refresh, or a stolen copy), `mfa_not_verified` (officer/admin refresh token that skipped the second step), `account_not_active` |
| `password_reset_requested` | `success` (`code_sent`), `ignored` (`no_account`, `cooldown`), `blocked` (`role_requires_admin_reset`) |
| `password_reset_completed` | `success` |
| `password_reset_failed` | `failure` (`invalid_or_expired_code`, `no_account`), `blocked` (`role_requires_admin_reset`) |
| `password_changed` | `success`; `detail: "other_sessions_revoked"` |
| `password_change_failed` | `failure`; `wrong_current_password`, `same_as_current` |
| `admin_password_reset` | `success`; `actor_id` is the admin who did it |
| `report_exported` | `success`; the account that downloaded a CSV/PDF report; `detail`: `<report> <csv\|pdf> rows=<n> total=<n>` — never the data itself |

---
  "next_expiry": {
    "instrument_type": "Weighing Machine",
    "uiid": "UIID-2024-0001",
    "valid_until": "2026-09-21T08:10:36+00:00",
    "days_remaining": 14
  }

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

Optional search filters (all roles that may list; combined with AND; they only narrow the role's own scope — see [Search filters](#search-filters)): `q`, `type` (exact instrument type; unknown → `400`), `state_code`, `district_code`.

### GET `/instruments/{instrument_id}`
Returns one instrument. Only its owner or an admin can view it.

---

## Applications

### POST `/applications` — role: `owner`
Submit a verification application for one of your own instruments.

**Body:** `{ "instrument_id": "...", "previous_certificate_id": "..." }` — `previous_certificate_id` is optional.
**Response** `201`: application with `status: "submitted"`, plus `application_type` (`"initial"` or `"renewal"`), `previous_certificate_id` and `previous_cert_no`. The server sets the type: an instrument that already has a certificate is a `renewal`, linked to `previous_certificate_id` or, if omitted, to its newest certificate.
**Errors:** `422` if `previous_certificate_id` is not a certificate of this instrument; `409` if the instrument already has an application in `submitted`, `scheduled` or `inspected`, or if re-verification has not opened yet (it opens `REVERIFY_WINDOW_DAYS`, default 30, before the newest certificate expires and stays open after). The application also returns `previous_valid_until`.

### GET `/applications`
Role-scoped:
- `owner` → their own applications
- `lmo` / `gatc` → the unclaimed queue (`status=submitted`, unassigned) by default; pass `?mine=true` to see applications assigned to them instead
- `admin` → everything

Optional query params for all roles: `?status=<status>` to filter by status, plus the search filters below (`q`, `application_type`, `instrument_type`, `state_code`, `district_code`, `date_from`, `date_to`). `date_from`/`date_to` are India calendar days of submission. `application_type` is `initial` or `renewal` (records from before re-verification count as `initial`).

### GET `/applications/{application_id}`
Returns one application with its full status `history[]`. Visible to its owner, its assigned officer, or an admin.

### POST `/applications/{application_id}/claim` — role: `lmo`, `gatc`
Self-claim an unassigned application from the queue **and book its inspection**. Sets `assigned_officer_id` to the calling officer, stores the schedule and transitions status `submitted → scheduled`.

**Body** (both required, otherwise `422`)
```json
{ "date": "2026-11-02", "slot": "morning" }
```
`date` is an India calendar date (`YYYY-MM-DD`); `slot` is `morning` (10:00-13:00) or `afternoon` (14:00-17:00).

Rules: no Sundays, no past dates, at most `SCHEDULE_MAX_AHEAD_DAYS` (60) ahead, and at most `SLOT_CAPACITY_PER_OFFICER` (4) inspections per officer per slot (`409` when full). Bad date/slot → `422`. Outside the officer's jurisdiction → `403`.

Claiming is atomic — if two officers hit this at the same instant, exactly one succeeds. Returns `409` if the application is already claimed by someone else, `404` if it doesn't exist.

### POST `/applications/{application_id}/schedule` — role: assigned `lmo`/`gatc`, or `admin`
Change the date or slot of a `scheduled` inspection. Body: `{ "date", "slot", "reason"? }`. Same date/slot/capacity rules as claim. `409` if the application is not `scheduled` or the slot is unchanged. Each change is appended to `schedule_history[]` (kind, date, slot, previous date/slot, who, reason) and the owner gets an email.

### POST `/applications/{application_id}/assign` — role: `admin`
Allocate a `submitted` application to a named officer, or move a `scheduled` one to another officer. Body: `{ "officer_id", "date", "slot", "reason"? }`. The officer must be active and the application must be inside their jurisdiction (`422` otherwise); capacity applies (`409`).

### GET `/applications/slots` — role: `lmo`, `gatc`, `admin`
Places left per date and slot for one officer, so the UI only offers bookable slots. Query: `start` (default today), `days` (1-62, default 14), `officer_id` (required for admins; officers can only see their own). Returns `days[]` with `date`, `bookable`, `reason` and `slots[]` (`slot`, `label`, `booked`, `capacity`, `available`).

Application responses now include `scheduled_date`, `slot`, `slot_label` and `schedule_history[]`.

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
  "photos": ["https://res.cloudinary.com/.../photo1.jpg"],
  "identity_method": "qr",
  "location": { "lat": 24.1, "lng": 88.25, "accuracy_m": 12 },
  "client_id": "6f1c2e0a-3b7d-4c55-9a52-1d2f8e7b9c01",
  "captured_at": "2026-10-16T09:41:00Z",
  "test_points": [
    { "reference": 10, "indicated": 10.02 },
    { "reference": 20, "indicated": 20.01 },
    { "reference": 30, "indicated": 30.03 }
  ],
  "checks": { "zero_ok": true, "display_ok": true, "level_stable": true, "markings_ok": true, "no_tampering": true },
  "seal_number": "WB/2026-0042"
}
```
`result` is `"pass"` or `"fail"`. `photos` is a list of URLs — upload each photo first via `POST /uploads/photo` to get these URLs.

`location` is **required** (`lat` −90…90, `lng` −180…180, `accuracy_m` optional) — a missing or out-of-range value returns `422`. `identity_method` is `"qr"` or `"manual"` (default `"manual"`).

**Detailed form — `test_points`, `checks`, `seal_number`.** What to record depends on the instrument type; `GET /inspections/form-spec?type=…` returns it (test title and unit, minimum number of readings, the checks and which are required). The server works out each reading's `error` (`indicated − reference`) and `error_pct` (of the reference; `null` when the reference is `0`). It does **not** decide pass/fail from the error: permitted errors depend on the instrument's class and rules, so the officer decides `result` and the numbers are the evidence.
- **Pass** needs at least `min_points` readings, an answer for every check with every `required` check `true`, and a `seal_number`. Otherwise `422` with a plain message (a required check that is not met means the officer should record a Fail).
- **Fail** needs none of these; anything sent is validated and stored. A `seal_number` on a Fail → `422` (no seal is fixed on a failed instrument).
- `seal_number`: trimmed, upper-cased, 3–32 characters (letters, digits, space, `/ . _ -`), **unique** across inspections — reuse → `409`. It is copied onto the certificate, printed on the PDF and returned by the verify endpoint.
- Readings: finite numbers within ±1,000,000,000, at most 12. Unknown check keys → `422`.
- With `INSPECTION_FORM_STRICT=false` the server also accepts a Pass without any of these (old app versions, inspections queued on phones before the upgrade). The default is strict: a Pass without them → `422` "This inspection form is out of date…". A replayed `client_id` always returns the stored record first, before any of this is checked.

**Offline / retry support (optional fields).** `client_id` (8–64 chars, letters, digits, `-`, `_`) is an idempotency key: if the same officer sends the same `client_id` again, the original inspection is returned with `200` and nothing is applied twice (no second status change, email or certificate). `captured_at` (ISO 8601) is when the officer really submitted on the device; it is used as the inspection time only when it is not in the future (5 min skew allowed) and not older than 14 days, otherwise the server time is used. The response's `submitted_offline` is `true` when the inspection reached the server more than a minute after it was captured.

**Requirements:** the application must currently be `scheduled` and assigned to you, or this returns `409` / `403`.

**Effect:** automatically transitions the application `scheduled → inspected → certified` (if `pass`) or `→ rejected` (if `fail`). On a pass, a certificate is generated and stored (see Certificates below). If certificate generation fails (e.g. Cloudinary is down), the inspection still succeeds and the application stays `certified` — the certificate can be regenerated separately, this endpoint won't fail because of it.

### GET `/inspections/form-spec?type={instrument type}` — role: `lmo`, `gatc`, `admin`
The form for one instrument type (`404` for an unknown type):
```json
{
  "form_version": 1,
  "instrument_type": "Fuel Dispensing Unit",
  "test": { "title": "Delivery test", "reference_label": "Quantity in the test measure", "indicated_label": "Quantity shown on the dispenser",
            "min_points": 2, "max_points": 12, "hint": "Deliver into a calibrated test measure. Record at least two deliveries.", "unit": "L" },
  "checks": [ { "key": "display_ok", "label": "Display or scale is clear and fully readable", "required": true } ],
  "seal": { "label": "Verification stamp / seal number", "required_on_pass": true }
}
```
The wording and the list per type live in `backend/app/config/inspection_forms.py`.

### GET `/inspections/by-application/{application_id}`
The latest inspection of an application (`404` if none). The officer who made it and admins see everything; the **instrument's owner** sees the result, readings, checks, seal number and notes, but `officer_id` and `location` are `null`. Anyone else → `403`.

### GET `/inspections/{inspection_id}`
Returns one inspection. Visible to the officer who submitted it, or an admin. The response now also carries `seal_number`, `test_points[]` (`reference`, `indicated`, `error`, `error_pct`), `checks[]` (`key`, `label`, `ok`) and `form` (`instrument_type`, `unit`, `test_title`, `reference_label`, `indicated_label`). On inspections made before the detailed form these are empty / `null`.

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

## Certificate validity

Role: `admin` only (owners, officers and anonymous callers get `403` / `401`). How long a **newly issued** certificate stays valid, per instrument type. A type without a rule gets `DEFAULT_CERT_VALIDITY_DAYS` (365). Certificates already issued are never changed: they keep the `valid_until` they were issued with, and the expiry reminders, re-verification window and enforcement lists all follow that date. A renewal issued while the old certificate is still valid still continues from the old expiry date, with the period of the instrument's type. Every change is audited (`validity_rule_changed`, `validity_rule_reset`).

### GET `/admin/validity`
```json
{
  "default_days": 365, "default_label": "1 year", "min_days": 30, "max_days": 3650,
  "items": [
    {"type": "Water Meter", "days": 730, "label": "2 years", "default_days": 365, "is_default": false,
     "updated_at": "2026-10-19T09:30:00Z", "updated_by_name": "Minister"},
    {"type": "Platform Scale", "days": 365, "label": "1 year", "default_days": 365, "is_default": true,
     "updated_at": null, "updated_by_name": null}
  ]
}
```
One item for every instrument type.

### PUT `/admin/validity/{instrument type}`
Body `{"days": 730}`. Returns the updated item. `422` if `days` is not a whole number between `min_days` and `max_days`; `404` for an unknown instrument type.

### DELETE `/admin/validity/{instrument type}`
Removes the type's own period so it uses the default again. Returns the item. `404` for an unknown type.

`GET /instruments/meta/types` (any signed-in user) also returns `validity_days` and `validity_label` for each type, so the registration form can show how long a certificate will last. Certificates carry `validity_days` as issued.

## Profile

Any signed-in user. `User` objects (login, `/auth/me`) also carry `avatar_url` (string or null).

### PATCH `/auth/me`
Body: any of `{"name", "contact", "org_name"}`; only the fields sent change. `contact` is a 10-digit mobile number starting 6-9, or `""` to clear it; changing it sets `is_phone_verified` to false. `org_name` is for owners only (`403` for officers/admins). Email, role and status cannot be changed. Returns the user. `422` for invalid values.

### POST `/auth/me/avatar`
Multipart `file`: JPG, PNG or WebP, up to 2 MB, checked by content. Replaces the previous picture. Returns the user. `413` too large, `415` wrong type, `400` empty, `502` if storage fails.

### DELETE `/auth/me/avatar`
Removes the picture. Returns the user.

## Required documents

An application needs its documents before it can be submitted. Slots (one file each, uploading again replaces it): `tax_invoice` and `owner_id_proof` for a first verification (the instrument has no certificate yet); `previous_certificate` for a re-verification. `POST /applications` answers `422` ("Upload the required documents first: …") until the required slots are filled. A previous-certificate copy uploaded before the newest certificate was issued does not count. While an application for the instrument is open (`submitted`, `scheduled`, `inspected`) the documents are locked (`409`).

### GET `/instruments/{id}/documents`
The instrument's owner, an admin, or an officer who can see the instrument (assigned, or in the unclaimed queue). Required slots come first.
```json
{"application_type": "initial", "complete": false, "locked": false,
 "slots": [
   {"slot": "tax_invoice", "label": "Tax invoice", "hint": "The purchase invoice for this instrument.", "required": true,
    "document": {"id": "…", "instrument_id": "…", "slot": "tax_invoice", "label": "Tax invoice", "filename": "Invoice.pdf",
                 "content_type": "application/pdf", "size": 120345, "url": "https://…", "uploaded_at": "2026-10-19T09:30:00Z"}},
   {"slot": "owner_id_proof", "label": "Owner ID proof", "hint": "…", "required": true, "document": null}
 ]}
```

### POST `/instruments/{id}/documents/{slot}`
Owner of the instrument only. Multipart `file`: PDF, JPG or PNG, up to 5 MB, checked by content. Replaces the slot's file. `422` if the slot isn't needed for this instrument's next application, `404` unknown slot, `409` locked, `413` / `415` / `400` as for the avatar. Audited.

### DELETE `/instruments/{id}/documents/{slot}`
Owner only. `204`; `404` if the slot is empty; `409` locked. Audited.

## Oversight

Read-only monitoring views. Role: `admin` (whole country), `lmo` / `gatc` (own jurisdiction, same rule as the application queue; an officer with no jurisdiction gets empty results). `owner` and anonymous → `403` / `401`. A `state_code` / `district_code` filter only narrows what the role may already see. Reads may come from a replica (`MONGO_READ_PREFERENCE`), so figures can lag a moment. Responses are not cached.

### GET `/oversight/pendency?state_code=&district_code=`
Open applications (`submitted`, `scheduled`, `inspected`) by age in whole **India calendar days** since `submitted_at` (submitted today IST = 0, yesterday = 1, whatever the time of day).
```json
{
  "generated_at": "2026-10-18T09:00:00+00:00",
  "target_days": 30,
  "total_open": 5, "unassigned": 3, "over_target": 2,
  "by_status": { "submitted": 3, "scheduled": 1, "inspected": 1 },
  "buckets": [
    { "label": "0-7 days", "min_days": 0, "max_days": 7, "count": 2,
      "by_status": { "submitted": 1, "scheduled": 1, "inspected": 0 } },
    { "label": "Over 60 days", "min_days": 61, "max_days": null, "count": 1, "by_status": { "submitted": 1, "scheduled": 0, "inspected": 0 } }
  ],
  "oldest": [
    { "application_id": "…", "uiid": "LM-26-00000001", "instrument_type": "Platform Scale", "status": "submitted",
      "application_type": "initial", "state_name": "Bihar", "district_name": "Patna",
      "submitted_at": "2026-04-01T06:00:00+00:00", "age_days": 200, "assigned": false }
  ]
}
```
Buckets are 0-7, 8-14, 15-30, 31-60 and over 60 days. `over_target` counts applications older than `PENDENCY_TARGET_DAYS` (default 30). `oldest` holds the ten longest waiting.

### GET `/oversight/districts?state_code=&district_code=`
One row per district with at least one instrument or application, most overdue first, plus `totals`.
```json
{
  "generated_at": "…", "target_days": 30,
  "totals": { "instruments": 4, "open_applications": 2, "overdue_applications": 1, "verified": 2, "expired": 1 },
  "rows": [
    { "state_code": "WB", "state_name": "West Bengal", "district_code": "319", "district_name": "Murshidabad",
      "instruments": 2, "open_applications": 2, "overdue_applications": 1, "verified": 2, "expired": 0 }
  ]
}
```
`verified` counts applications in `certified` / `expiring`; `expired` counts applications in `expired`.

### GET `/oversight/enforcement`
Instruments whose **newest** certificate has run out, longest lapsed first.

| Query | Meaning |
|-------|---------|
| `state_code`, `district_code` | Narrow the place |
| `reverification` | `applied` (an open application exists) or `none` |
| `min_days_overdue` | Only instruments lapsed at least this many days (0-36500) |
| `page`, `page_size` | Default 1 and 25; `page_size` max 100. Anything else → `422` |

```json
{
  "generated_at": "…",
  "summary": { "lapsed": 3, "reverification_applied": 1, "no_reverification": 2, "recent": 1, "overdue": 1, "long_overdue": 1 },
  "total": 3, "page": 1, "page_size": 25, "truncated": false,
  "items": [
    { "instrument_id": "…", "uiid": "LM-26-00000007", "instrument_type": "Platform Scale",
      "owner_name": "Anil", "org_name": "Alpha Traders", "address_line": "Main Road",
      "state_code": "WB", "state_name": "West Bengal", "district_code": "319", "district_name": "Murshidabad",
      "cert_no": "CERT-20250101-ABC123", "valid_until": "2026-06-20T00:00:00+00:00",
      "days_overdue": 120, "band": "long_overdue",
      "reverification": { "status": "scheduled", "applied_on": "2026-10-16T06:00:00+00:00" },
      "case": { "id": "…", "status": "notice_sent", "level": "lmo" } }
  ]
}
```
`band` is `recent` (up to 30 days lapsed), `overdue` (31-90) or `long_overdue` (over 90). `summary` covers every match, not just the page. `reverification` is `null` when no re-verification application is open; when present it is a mitigating note, the certificate is still not in force. An instrument with a newer valid certificate is not listed, and neither is one that was never certified. Owner contact details are not returned. `truncated` is `true` only when more than `ENFORCEMENT_MAX_SCAN` (default 50000) instruments are lapsed in scope; the most overdue are kept. Based on each instrument's newest certificate (`valid_until` in the past), not on application status, so it does not wait for the hourly expiry job; the place is the instrument's registered state / district.

`case` is the open enforcement case on the instrument (`open`, `notice_sent` or `escalated`; `level` is who holds it), or `null`.

### GET `/oversight/uncertified`
Instruments registered more than `NEVER_CERTIFIED_GRACE_DAYS` (default 30) India calendar days ago that have **no certificate at all**, longest registered first. Same access and place rules as the other oversight endpoints.

| Query | Meaning |
|-------|---------|
| `state_code`, `district_code` | Narrow the place |
| `application` | `applied` (an open application exists) or `none` |
| `min_days` | Only instruments registered at least this many days ago (0-36500) |
| `page`, `page_size` | Default 1 and 25; `page_size` max 100 |

```json
{
  "generated_at": "…", "grace_days": 30,
  "summary": { "total": 2, "applied": 1, "not_applied": 1 },
  "total": 2, "page": 1, "page_size": 25, "truncated": false,
  "items": [
    { "instrument_id": "…", "uiid": "LM-26-00000011", "instrument_type": "Platform Scale",
      "owner_name": "Anil", "org_name": "Alpha Traders", "address_line": "Main Road",
      "state_code": "WB", "state_name": "West Bengal", "district_code": "319", "district_name": "Murshidabad",
      "registered_on": "2026-08-20T07:00:00+00:00", "days_since_registered": 59,
      "application": { "status": "scheduled", "applied_on": "2026-10-10T06:00:00+00:00" },
      "case": null }
  ]
}
```
The registration time is read from the instrument's ObjectId (instruments carry no date field). `application` is an open application (a mitigating note); `truncated` is `true` only if more than `ENFORCEMENT_MAX_SCAN` instruments match.

### Enforcement cases
Roles `admin`, `lmo`, `gatc` (owners get `403`). A case belongs to one instrument (one active case at a time) and has a timeline. `kind` is `lapsed` or `never_certified`; `status` is `open`, `notice_sent`, `escalated` or `resolved`; `level` is `lmo`, `gatc` or `admin` (who holds it). Cases outside the caller's jurisdiction are `404`.

| Endpoint | What it does |
|----------|--------------|
| `POST /oversight/cases` `{ "instrument_id" }` | Open a case. The instrument must be on one of the two lists (else `409`) and in the caller's jurisdiction (else `404`). Opening again returns the same case. The case starts at the opener's level. |
| `GET /oversight/cases` | List. Query: `status` (`active` default, `open`, `notice_sent`, `escalated`, `resolved`, `all`), `kind`, `due=true` (due for escalation), `with_me=true`, `state_code`, `district_code`, `page`, `page_size`. Returns `summary` counts (`active`, `open`, `notice_sent`, `escalated`, `escalation_due`, `with_me`, `resolved`) and `items`. |
| `GET /oversight/cases/{id}` | One case with `events` (opened / notice / note / escalated / resolved, newest last), `can` (`note`, `notice`, `escalate`, `close`, `notice_available_on`) and the certificate or registration facts. |
| `POST /oversight/cases/{id}/notice` `{ "message"? }` | Record and email a notice to the owner. Only the level holding the case, or an admin (else `403`). `409` if resolved, or if a notice was sent within `NOTICE_MIN_GAP_DAYS` days. Recorded even when no email could be sent (`emailed: false`). |
| `POST /oversight/cases/{id}/note` `{ "text" }` | Internal note; any officer in the jurisdiction. |
| `POST /oversight/cases/{id}/escalate` `{ "reason"? }` | Move up one level (`lmo` to `gatc` to `admin`). Holder or admin only; `409` at admin level. |
| `POST /oversight/cases/{id}/close` `{ "reason" }` | Close with a reason. Holder or admin only. |

`escalation_due` is `true` when the status is `notice_sent`, the last notice is at least `ESCALATION_AFTER_DAYS` (default 15) India calendar days old and the level is not `admin`; the hourly job then escalates the case automatically (the timeline shows the system did it). A case also resolves itself (`resolution` `renewed` or `certified`) when the instrument gets a valid certificate. Opening, notices, escalations and closures are audit-logged (`enforcement_case_opened`, `enforcement_notice_sent`, `enforcement_case_escalated`, `enforcement_case_closed`). Owner contact details are never returned.

### GET `/notices/mine` — owner
The latest notice on each of the owner's instruments whose case is still open, newest first (up to 50). Each item: `case_id`, `kind`, `instrument_id`, `uiid`, `instrument_type`, `sent_at`, `message`, `issued_by` (a role title such as "Legal Metrology Officer", never a person's name) and `notice_count`. Internal notes are not included. A notice disappears once the case is resolved.

---

## Certificates

### GET `/certificates/verify/{cert_id}` — **public**, no auth
Powers verify-page's `[certId].jsx`. This is the locked response contract confirmed with Aritra/Anushka — don't change the shape without telling them.
```json
{
  "valid": true,
  "certificate": {
    "id": "...",
    "seal_number": "WB/2026-0042",
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

Optional search filters: `q` (certificate number, seal number, the number it renews, the certificate id, or the instrument's UIID / serial number / manufacturer / model / type), `status` (`valid` / `expiring` / `expired` — `expiring` means still valid but within the first expiry-reminder window, 30 days by default), `application_type`, `instrument_type`, `date_from`, `date_to` (India days of issue). See [Search filters](#search-filters).

---

## Search filters

Used by `GET /applications`, `GET /certificates/`, `GET /instruments`, `GET /admin/users` and the matching [reports](#reports). All are optional and combine with AND; omitting them returns exactly what the endpoint returned before filters existed.

- **Scope first, filters second.** What a role may see (owner → own records, officer → their jurisdiction or queue, admin → everything) is decided before any filter is applied. A filter can only narrow it: an owner searching for someone else's UIID gets an empty list, an officer filtering on another district gets an empty list.
- `q` — free text, max 100 characters, trimmed. Matched case-insensitively as a *literal* substring (`.*` or `(` are ordinary characters, never a pattern). Which fields it searches is listed under each endpoint.
- `date_from`, `date_to` — `YYYY-MM-DD`, both days inclusive, **India time** (a record submitted at 01:30 IST on 18 Oct counts as 18 Oct). `date_from` after `date_to` → `400`; a malformed date → `422`. (The audit log keeps its own UTC days.)
- `instrument_type` / `type` — an exact value from `GET /instruments/meta/types`; anything else → `400`.
- Text and type filters on applications and certificates are answered by first finding up to 10,000 matching instruments; a filter broader than that (for example every scale in the country) should be narrowed with a state or district.
- `GET /admin/users` (admin): `q` (name, email or organisation), `role` (`lmo` / `gatc`), `status` (`pending` / `active` / `rejected`; accounts with no status count as active).

---

## Reports

### GET `/reports/applications` · `/reports/certificates` · `/reports/instruments` · `/reports/audit-logs` · `/reports/oversight-pendency` · `/reports/oversight-districts` · `/reports/oversight-enforcement` · `/reports/oversight-uncertified`
Downloads the rows of the matching list as a file. Same roles, same scoping and same filters as the list (`/reports/applications` also takes `mine=true`, like the list; `/reports/instruments` is for `owner` and `admin` only, `403` otherwise; `/reports/audit-logs` is `admin` only and takes the audit viewer's filters — `event`, `outcome`, `role`, `search`, `date_from`, `date_to` in UTC days). `/reports/oversight-pendency`, `/reports/oversight-districts`, `/reports/oversight-enforcement` and `/reports/oversight-uncertified` are for `admin`, `lmo` and `gatc` (owners get `403`), take the same `state_code` / `district_code` (and, for enforcement, `reverification` and `min_days_overdue`) as the Oversight endpoints, and apply the same jurisdiction rules. When more than `REPORT_MAX_ROWS` rows match, the file keeps the longest-waiting (pendency) or most overdue (enforcement) rows and `X-Report-Truncated` is `true`. Owner contact details are never included.

| Query parameter | Meaning |
|---|---|
| `format` | `csv` (default) or `pdf`; anything else → `422` |
| …the list's filters | see [Search filters](#search-filters) |

**Response** `200`: the file, with `Content-Disposition: attachment; filename="maapsetu-<report>-<YYYYMMDD-HHMM>.<ext>"` (India time) and `Cache-Control: no-store`.

| Header | Meaning |
|---|---|
| `X-Report-Rows` | rows in the file |
| `X-Report-Total` | rows that matched |
| `X-Report-Truncated` | `true` when more matched than `REPORT_MAX_ROWS` (default 5000); the file then holds the **newest** rows (PDF: with a note) |
| `Access-Control-Expose-Headers` | lists the above so a browser app can read them |

- **CSV**: UTF-8 with a byte-order mark, header row, every column. Cells that start with `=`, `+`, `-`, `@`, tab or carriage return are prefixed with `'` so a spreadsheet shows them as text instead of running them.
- **PDF**: A4 landscape summary (fewer columns than the CSV) with title, who generated it, time (IST), filters used, record count, repeating table header and page numbers. Characters outside Windows-1252 print as `?`.
- Columns: *applications* — application ID, type, status, instrument UIID / type / manufacturer / model / serial, state, district, applied on, inspection date and slot, certificate renewed, its expiry (+ assigned officer and owner organisation for admins). *certificates* — certificate no., status (Valid / Expiring soon / Expired), instrument details, seal no., place, type, certificate renewed, verified on, valid from / until (+ owner organisation for admins). *instruments* — UIID, type, manufacturer, model, capacity, serial, place, address, latest certificate and its status (Valid / Expiring soon / Expired / Not yet verified) (+ owner organisation for admins). *audit-logs* — time (IST), event, outcome, account, role, done by, IP address, detail.
- Rate limit: `20/10minutes` per IP (`429`). Every successful download is written to the audit log as `report_exported` (account, role, and `detail` like `applications csv rows=120 total=120`); a refused request is not.

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