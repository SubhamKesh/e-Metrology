import re

# --- Email addresses -------------------------------------------------------
#
# Same shape check the frontend already uses (see
# frontend/src/lib/validation.ts: isValidEmail) — kept in sync deliberately
# so a rejected email gets the same friendly message on both sides instead
# of the frontend's simple check passing something the backend's stricter
# EmailStr then bounces with the technical "part after the @-sign..."
# message. Deliberately looser than full RFC 5322 / EmailStr's
# email-validator library — good enough to catch typos, not meant to be a
# mailbox-existence check.
EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def validate_email(value: str) -> str:
    value = value.strip().lower()
    if not EMAIL_REGEX.match(value):
        raise ValueError("Enter a valid email address.")
    return value


# --- Phone numbers -------------------------------------------------------
#
# India: exactly 10 digits, no +91 or other prefix, and must start with
# 6-9 — Indian mobile numbers are never issued starting with 0-5, so this
# also rules out a leading 0 specifically. Kept as a plain regex (not
# pydantic's constr(regex=...)) so the same check can be reused as a
# plain function from multiple models without depending on which pydantic
# major version is installed (v1 uses `regex=`, v2 uses `pattern=` on
# Field/constr — a bare function + @validator works the same on both).
PHONE_REGEX = re.compile(r"^[6-9]\d{9}$")


def validate_phone(value):
    """Validator for an Optional[str] `contact` field. Empty string is
    treated the same as "not provided" (normalized to None) rather than
    rejected outright, since a form field left blank shouldn't behave
    differently from the field being omitted entirely."""
    if value is None:
        return None
    value = value.strip()
    if value == "":
        return None
    if not PHONE_REGEX.match(value):
        raise ValueError(
            "contact must be exactly 10 digits, starting with 6-9, e.g. '9876543210' (no +91 or other prefix)"
        )
    return value


# --- Free-text length bounds ----------------------------------------------
#
# Applied via Field(max_length=...) at the point each field is declared.
# Centralized here so every field of a given "kind" (a name, an address, a
# long note) uses the same bound instead of each model picking its own
# number.
MAX_SHORT_TEXT = 100   # names, manufacturer, model, serial_no
MAX_LONG_TEXT = 200    # address_line, org_name
MAX_NOTE_TEXT = 2000   # observations, free-form notes


def _validate_max_length(value: str, max_len: int, label: str) -> str:
    """Shared by the field-specific validate_* functions below — same
    length check, different label so each field's error names itself
    instead of a generic 'this field' message."""
    value = value.strip()
    if len(value) > max_len:
        raise ValueError(f"{label} must be at most {max_len} characters.")
    return value


def validate_model(value: str) -> str:
    """Friendlier message than Pydantic's default max_length error for
    the instrument model field. Same MAX_SHORT_TEXT bound, just phrased
    for an owner filling out a form rather than an API consumer."""
    return _validate_max_length(value, MAX_SHORT_TEXT, "Model")


def validate_name(value: str) -> str:
    return _validate_max_length(value, MAX_SHORT_TEXT, "Name")


def validate_manufacturer(value: str) -> str:
    return _validate_max_length(value, MAX_SHORT_TEXT, "Manufacturer")


def validate_serial_no(value: str) -> str:
    return _validate_max_length(value, MAX_SHORT_TEXT, "Serial number")


def validate_org_name(value):
    """org_name is Optional[str] on every model that has it — None passes
    straight through, same as validate_phone does for an unset contact."""
    if value is None:
        return None
    return _validate_max_length(value, MAX_LONG_TEXT, "Organisation name")


# Geo codes (state_code/district_code) are short fixed-format identifiers,
# not free text — bounded tightly so nothing can smuggle a large string
# into what should be a lookup key.
MAX_CODE_LENGTH = 10


def validate_address(value: str) -> str:
    """Friendlier message than Pydantic's default max_length error for
    address_line. Same MAX_LONG_TEXT bound, just phrased for an owner
    filling out a form rather than an API consumer."""
    value = value.strip()
    if len(value) > MAX_LONG_TEXT:
        raise ValueError(f"Address is too long — please keep it under {MAX_LONG_TEXT} characters.")
    return value


# --- Passwords ---------------------------------------------------------
#
# Same MIN_PASSWORD_LENGTH bound as Field(min_length=6) enforced before,
# just with a message in plain words. Used for both the initial password
# on signup and a new password on change — same rule either way.
MIN_PASSWORD_LENGTH = 6


def validate_password(value: str) -> str:
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    return value


# --- Instrument capacity ---------------------------------------------------
#
# The client submits just the bare number (e.g. "30"); the unit is looked
# up from app/config/instrument_specs.py and appended server-side (see
# routers/instruments.py: register_instrument). This validator only checks
# that what was submitted is a plausible positive number.
CAPACITY_NUMBER_REGEX = re.compile(r"^\d+(\.\d+)?$")
CAPACITY_MAX_VALUE = 1_000_000  # generous upper bound — rejects absurd/typo'd values, not type-specific


def validate_capacity_number(value: str) -> str:
    value = value.strip()
    if not CAPACITY_NUMBER_REGEX.match(value):
        raise ValueError('capacity must be a positive number, e.g. "30" — the unit is added automatically')
    number = float(value)
    if number <= 0:
        raise ValueError("capacity must be greater than 0")
    if number > CAPACITY_MAX_VALUE:
        raise ValueError("capacity value is unrealistically large")
    return value