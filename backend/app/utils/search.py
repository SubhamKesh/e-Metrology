"""Shared building blocks for the list-search filters and the report exports.

Kept free of database access so they can be tested on their own. Every filter
is optional; an absent filter changes nothing, so existing API clients that
send none of them get exactly the lists they got before.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Optional

from fastapi import HTTPException, Query

IST = timezone(timedelta(hours=5, minutes=30))

MAX_QUERY_LENGTH = 100

# A text search or instrument-type filter on a list of applications/certificates is answered by first
# finding the matching instruments. This bounds that step. Searches are meant to be specific; a filter
# that matches more instruments than this (for example "every scale in the country") is narrowed with a
# state or district first.
MAX_INSTRUMENT_MATCHES = 10_000

# --- Query parameter types, shared by the list endpoints and the report endpoints. -----------------
# Annotated (rather than `= Query(...)` as the default) so calling a route function directly, as the
# tests do, still gets a plain None for a filter that was not passed.
SearchText = Annotated[
    Optional[str],
    Query(max_length=MAX_QUERY_LENGTH, description="Free-text search (case-insensitive, matched literally)"),
]
DateFrom = Annotated[Optional[date], Query(description="First day to include, YYYY-MM-DD (India time)")]
DateTo = Annotated[Optional[date], Query(description="Last day to include, YYYY-MM-DD (India time)")]
InstrumentTypeParam = Annotated[Optional[str], Query(max_length=60, description="Exact instrument type")]
StateCodeParam = Annotated[Optional[str], Query(max_length=16)]
DistrictCodeParam = Annotated[Optional[str], Query(max_length=16)]


def clean_query(text: Optional[str]) -> Optional[str]:
    """Trimmed search text with inner whitespace collapsed, or None when nothing is left."""
    if text is None:
        return None
    cleaned = " ".join(str(text).split())
    return cleaned or None


def contains(text: str) -> dict:
    """Case-insensitive 'contains' match. The text is escaped, so it is matched literally and can never
    act as a regular expression."""
    return {"$regex": re.escape(text), "$options": "i"}


def utc_naive(value: datetime) -> datetime:
    """UTC wall-clock time without a tzinfo: how MongoDB hands datetimes back, and how it reads a bare
    datetime in a query. Comparing like with like keeps range filters identical on every driver."""
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def now_utc_naive() -> datetime:
    return utc_naive(datetime.now(timezone.utc))


def ist_window(date_from: Optional[date], date_to: Optional[date]) -> Optional[dict]:
    """Mongo range (UTC) covering the India calendar days date_from..date_to inclusive.

    Officials think in India dates, so "17 Oct" means 17 Oct 00:00 to 24:00 IST, not UTC.
    Returns None when neither bound is given; raises 400 when the range is back to front.
    """
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="'From' date must not be after 'To' date.")
    window: dict = {}
    if date_from:
        window["$gte"] = utc_naive(datetime.combine(date_from, time.min, tzinfo=IST))
    if date_to:
        window["$lt"] = utc_naive(datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=IST))
    return window or None


def instrument_filter(
    text: Optional[str] = None,
    instrument_type: Optional[str] = None,
    state_code: Optional[str] = None,
    district_code: Optional[str] = None,
) -> dict:
    """Mongo filter on the instruments collection for the free-text box and the type / place filters.

    Text matches the instrument's UIID, serial number, manufacturer, model or type.
    """
    clauses: list[dict] = []
    text = clean_query(text)
    if text:
        pattern = contains(text)
        clauses.append({"$or": [
            {"uiid": pattern}, {"serial_no": pattern}, {"manufacturer": pattern},
            {"model": pattern}, {"type": pattern},
        ]})
    if instrument_type:
        clauses.append({"type": instrument_type})
    if state_code:
        clauses.append({"location.state_code": state_code})
    if district_code:
        clauses.append({"location.district_code": district_code})
    if not clauses:
        return {}
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def combine(scope: dict, extra: list[dict]) -> dict:
    """`scope` (who may see the rows) AND every clause in `extra` (what the user asked for).

    With no extra clauses the scope is returned untouched, so an unfiltered request runs the very same
    query as before filters existed.
    """
    extra = [c for c in extra if c]
    if not extra:
        return scope
    parts = ([scope] if scope else []) + extra
    return parts[0] if len(parts) == 1 else {"$and": parts}


def check_instrument_type(instrument_type: Optional[str], allowed: list[str]) -> Optional[str]:
    if instrument_type and instrument_type not in allowed:
        raise HTTPException(status_code=400, detail="Unknown instrument type.")
    return instrument_type
