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

### Audit log
Security events are written to the `audit_logs` collection (retained `AUDIT_LOG_RETENTION_DAYS`, default 365, minimum 180) and to the `app.audit` log stream. Records hold the event, outcome (`success` / `failure` / `blocked` / `ignored`), account email / id / role, acting admin (if any), client IP, user agent and a short reason — never passwords, reset codes or tokens. Writing a record is best-effort: a logging failure never fails the request.

| Event | Outcomes / `detail` values |
|---|---|
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