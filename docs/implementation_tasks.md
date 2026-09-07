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

## Suggested process for the team

1. Implement frontend changes and test locally (Register + Login + RegisterInstrument pages).
2. Add backend validation and run backend unit/manual tests to ensure requests with invalid `type` are rejected.
3. Merge frontend and backend changes together to avoid mismatched behavior.

If you want, I can produce small code snippets for any of the above files to accelerate the work.

---

File created by the repository assistant to help coordinate the change.
