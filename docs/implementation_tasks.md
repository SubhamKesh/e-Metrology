# Implementation tasks — small frontend + backend changes

This document lists the exact files and concise instructions for two small changes your team requested:

- Input validation on auth forms (name, mobile, email)
- Replace free-text `Instrument type` with a controlled dropdown and enforce allowed types server-side

---

## 1) Input validation (name / mobile / email)

Goal: show inline errors when invalid values are entered on the registration/login pages.

Files to edit (frontend):

- `frontend/src/pages/auth/Register.tsx` — add per-field error state and validation logic for:
  - `name`: allow letters and spaces only — regex `/^[A-Za-z\s]+$/`
  - `contact` (mobile): digits only, max 10 — allow typing up to 10 digits; on submit require exactly 10 digits `/^\d{10}$/`
  - `email`: basic format check `/^[^\s@]+@[^\s@]+\.[^\s@]+$/`
  - Show field errors by passing an error string to the `TextInput` `error` prop (component defined in `frontend/src/components/ui/Field.tsx`).

- `frontend/src/pages/auth/Login.tsx` — validate `email` format before calling `login()` and show inline error if invalid.

Optional shared helper:

- `frontend/src/lib/validation.ts` (create) — export small helpers: `isValidName`, `isValidEmail`, `isValidPhone` and import them in the pages.

Notes:
- `TextInput` already accepts an `error` prop (see `frontend/src/components/ui/Field.tsx`), so UI changes are minimal.
- Validate on both `onChange` (for immediate feedback) and on submit (final check before API call).

---

## 2) Instrument type dropdown + server validation

Goal: restrict `Instrument.type` to an allowed list on the UI and enforce the same list on the backend.

Allowed instrument list (exact strings to present in dropdown):

- water meters
- clinical thermometers
- automatic rail weighbridges
- tape measures
- non-automatic weighing instruments
- load cells
- beam scales
- counter machines
- weights
- gas meters
- energy meters
- moisture meters
- speed meters
- breath analysers
- flow meters

Files to edit (frontend):

- `frontend/src/pages/owner/RegisterInstrument.tsx` — replace the `TextInput` for `Instrument type` with `SelectInput` (provided by `frontend/src/components/ui/Field.tsx`) and pass the above list as `options`.
  - Example: `options={[{ value: 'water meters', label: 'water meters' }, ...]}`
  - Keep `required` and preserve the existing form submission flow.

Optional frontend improvements:
- Update `frontend/src/lib/types.ts` to change the `Instrument` type to a union or an enum to get TypeScript validation.

Files to edit (backend):

- `backend/app/models/instrument.py` — replace `type: str` in `InstrumentCreate` with a constrained type (Pydantic `Literal` or an `Enum`) or add validator to ensure `type` is one of the allowed strings.
  - Example: `from typing import Literal` then `type: Literal['water meters', 'clinical thermometers', ...]`

- `backend/app/routers/instruments.py` — add defensive check when creating instruments: if `payload.type` not in allowed list, raise `HTTPException(status_code=400, detail='Invalid instrument type')`.

Also update (if used):
- `backend/seed/seed_data.py` — update any seeded instrument entries to use allowed values.

---

## 3) Password recovery, remember-me & session security — DONE

Implemented (see `docs/api-contract.md` for the endpoint contract and `docs/security-hardening-status.md` for the rationale). Files touched:

Backend:
- `backend/app/routers/auth.py` — remember-me (owner-only), `/forgot-password`, `/reset-password`, change-password signs out other sessions, login/logout/refresh audit events
- `backend/app/routers/admin_users.py` — `POST /admin/users/{id}/reset-password` (admin resets an officer)
- `backend/app/utils/validators.py` — password policy (8–64 chars, upper/lower/digit/special, common-password list)
- `backend/app/services/audit.py` *(new)* — audit-log writer; `backend/app/config/db.py` creates the `audit_logs` collection + TTL index
- `backend/app/services/otp.py`, `mailer.py`, `jobs.py` — reset-code helpers, "password changed" + admin-reset emails
- `backend/app/models/user.py`, `utils/security.py`, `config/settings.py` — new request/response models, token expiry argument, new settings
- `backend/seed_super_admin.py` — validates the password policy; re-running it is the recovery path for the admin account
- Tests: `backend/tests/test_password_reset_and_remember_me.py`, `test_govt_hardening.py`, `test_sessions_and_login_audit.py` (all new); `conftest.py` points the audit collection at the in-memory DB

Frontend:
- `frontend/src/pages/auth/ForgotPassword.tsx` *(new)*, route in `App.tsx`; `Login.tsx` (remember-me checkbox, forgot link)
- `frontend/src/components/ui/PasswordRequirements.tsx` *(new)* + `lib/validation.ts` — shared password rules used by `Register.tsx`, `ChangePassword.tsx`, `ForgotPassword.tsx`
- `frontend/src/context/AuthContext.tsx`, `lib/api.ts`, `lib/endpoints.ts` — session restore on load, remember-me storage, fresh token after change-password
- `frontend/src/pages/admin/Users.tsx` — "Reset password" button for officers

---

## 4) Two-step verification & account-lifecycle audit — DONE

Officer and admin accounts must pass a TOTP (authenticator app) second step; registration, officer creation, approve and suspend are audit-logged; suspending now ends sessions. Contract: `docs/api-contract.md`; rationale and limits: `docs/security-hardening-status.md`. Files touched:

Backend:
- `backend/app/routers/auth.py` — login returns an `mfa_token` instead of a session for officer/admin; `POST /auth/mfa/setup`, `/mfa/confirm-setup`, `/mfa/verify`; refresh requires the second-step mark and refuses inactive accounts; registration audit events
- `backend/app/routers/admin_users.py` — `POST /admin/users/{id}/reset-mfa`; audit events for officer creation / approve / suspend; suspend revokes sessions; `mfa_enabled` in officer lists
- `backend/app/utils/totp.py` *(new)* — RFC 6238 TOTP; `backend/app/utils/mfa.py` *(new)* — secret encryption, recovery codes, QR code
- `backend/app/utils/security.py` — `create_mfa_token` / `decode_mfa_token`; `backend/app/config/settings.py` — `MFA_*` settings; `backend/app/models/user.py` — `LoginResponse`, MFA request/response models, `mfa_enabled`
- `backend/reset_mfa.py` *(new)* — operator tool for a lost admin authenticator; `backend/requirements.txt` — adds `cryptography`; `backend/.env.example`
- Tests: `backend/tests/test_mfa.py` *(new)*, `backend/tests/mfa_helpers.py` *(new)*; `conftest.py` gives every test a fresh DDoS counter; `test_govt_hardening.py` and `test_sessions_and_login_audit.py` now sign officers in through the second step

Frontend:
- `frontend/src/pages/auth/TwoFactor.tsx` *(new)* — code entry, recovery-code entry, authenticator setup (QR + manual key), recovery-code screen; route `/two-step` in `App.tsx`
- `frontend/src/context/AuthContext.tsx` — `login` can return "second step needed"; `verifyMfa`, `beginMfaSetup`, `confirmMfaSetup`, `commitSession`
- `frontend/src/pages/auth/Login.tsx` — hands off to `/two-step`; `frontend/src/lib/endpoints.ts`, `frontend/src/lib/types.ts` — new API calls and types
- `frontend/src/pages/admin/Users.tsx` — "2-step" status column and "Reset 2-step" button

---

## Suggested process for the team

1. Implement frontend changes and test locally (Register + Login + RegisterInstrument pages).
2. Add backend validation and run backend unit/manual tests to ensure requests with invalid `type` are rejected.
3. Merge frontend and backend changes together to avoid mismatched behavior.

If you want, I can produce small code snippets for any of the above files to accelerate the work.

---

File created by the repository assistant to help coordinate the change.
