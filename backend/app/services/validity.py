"""How long a certificate is valid, per instrument type.

Every type uses DEFAULT_CERT_VALIDITY_DAYS (365) unless an admin has given it a period of its own
(Admin -> Certificate validity, routers/admin_validity.py). Rules live in the `validity_rules`
collection, one document per type that differs from the default, so a change needs no deploy.

A rule is read when a certificate is issued and the result is written onto the certificate
(`valid_until`, plus `validity_days` for the record). Changing a rule therefore never touches a
certificate that already exists: its expiry, reminders, re-verification window and enforcement
status keep following the date printed on it.
"""
from __future__ import annotations

from typing import Optional

from app.config.db import validity_rules_col
from app.config.settings import DEFAULT_CERT_VALIDITY_DAYS

# Sanity limits for what an admin may enter. The lower one keeps a new certificate from being inside
# the 30-day expiry-reminder window the moment it is issued.
MIN_VALIDITY_DAYS = 30
MAX_VALIDITY_DAYS = 3650  # ten years


def default_days() -> int:
    return DEFAULT_CERT_VALIDITY_DAYS


def rules() -> dict[str, dict]:
    """{instrument type: rule document} for every type with a rule of its own."""
    return {r["type"]: r for r in validity_rules_col.find({})}


def validity_days_for(instrument_type: Optional[str]) -> int:
    """Days a certificate issued now for this instrument type stays valid."""
    if not instrument_type:
        return default_days()
    rule = validity_rules_col.find_one({"type": instrument_type})
    return int(rule["days"]) if rule else default_days()


def label(days: int) -> str:
    """'1 year', '2 years' when it is whole years, otherwise 'N days'."""
    if days % 365 == 0:
        years = days // 365
        return f"{years} year" if years == 1 else f"{years} years"
    return f"{days} day" if days == 1 else f"{days} days"
