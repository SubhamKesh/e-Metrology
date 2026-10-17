"""
Inspection scheduling rules. Pure helpers plus two small DB reads, so the
rules live in one place and every endpoint (claim, schedule/reschedule,
admin assign, slot availability) applies exactly the same checks.

Model
  * A schedule is plain data on the application: `scheduled_date` (an India
    calendar date, "YYYY-MM-DD") and `slot` ("morning" | "afternoon").
  * Two slots a day, Sundays off.
  * Each officer can take SLOT_CAPACITY_PER_OFFICER inspections per slot.
  * Every change is appended to `schedule_history` (never rewritten).

Dates are India time (IST has no daylight saving, so a fixed offset is exact).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

from app.config import settings

IST = timezone(timedelta(hours=5, minutes=30))

SLOTS = {
    "morning": {"label": "Morning (10:00 AM - 1:00 PM)", "start": (10, 0), "end": (13, 0)},
    "afternoon": {"label": "Afternoon (2:00 PM - 5:00 PM)", "start": (14, 0), "end": (17, 0)},
}

# Application statuses in which the inspection still holds its slot.
HOLDING_STATUSES = ["scheduled"]


def today_ist() -> date:
    return datetime.now(IST).date()


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Date must be in YYYY-MM-DD format")


def validate_slot_name(slot: str) -> str:
    if slot not in SLOTS:
        raise HTTPException(status_code=422, detail=f"Slot must be one of: {', '.join(SLOTS)}")
    return slot


def date_problem(day: date) -> Optional[str]:
    """Why this date cannot be booked, or None if it can."""
    today = today_ist()
    # Range first, Sunday last: a date that is out of range says so even when it falls on a Sunday.
    if day < today + timedelta(days=settings.SCHEDULE_MIN_LEAD_DAYS):
        return "That date is too soon" if settings.SCHEDULE_MIN_LEAD_DAYS else "That date has already passed"
    if day > today + timedelta(days=settings.SCHEDULE_MAX_AHEAD_DAYS):
        return f"Inspections can be booked at most {settings.SCHEDULE_MAX_AHEAD_DAYS} days ahead"
    if day.weekday() == 6:
        return "Inspections are not held on Sundays"
    return None


def slot_label(slot: Optional[str]) -> Optional[str]:
    return SLOTS[slot]["label"] if slot in SLOTS else None


def slot_window(day: str, slot: str) -> tuple[datetime, datetime]:
    """Start and end of a booked slot as timezone-aware datetimes (used for calendar files)."""
    d = date.fromisoformat(day)
    (sh, sm), (eh, em) = SLOTS[slot]["start"], SLOTS[slot]["end"]
    return (
        datetime(d.year, d.month, d.day, sh, sm, tzinfo=IST),
        datetime(d.year, d.month, d.day, eh, em, tzinfo=IST),
    )


def booked_count(applications_col, officer_id, day: str, slot: str, *, exclude_application=None) -> int:
    query: dict = {
        "assigned_officer_id": officer_id,
        "scheduled_date": day,
        "slot": slot,
        "status": {"$in": HOLDING_STATUSES},
    }
    if exclude_application is not None:
        query["_id"] = {"$ne": exclude_application}
    return applications_col.count_documents(query)


def check_bookable(applications_col, officer_id, day_str: str, slot: str, *, exclude_application=None) -> None:
    """Raise 422 (bad date/slot) or 409 (slot full). Returns None when it is fine."""
    validate_slot_name(slot)
    problem = date_problem(parse_date(day_str))
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    if booked_count(applications_col, officer_id, day_str, slot, exclude_application=exclude_application) \
            >= settings.SLOT_CAPACITY_PER_OFFICER:
        raise HTTPException(
            status_code=409,
            detail=f"That slot is full for this officer ({settings.SLOT_CAPACITY_PER_OFFICER} inspections). Pick another slot or date.",
        )


def slot_still_within_capacity(applications_col, officer_id, day: str, slot: str) -> bool:
    """Second check after a write, so two requests racing for the last place cannot both keep it."""
    return booked_count(applications_col, officer_id, day, slot) <= settings.SLOT_CAPACITY_PER_OFFICER


def availability(applications_col, officer_id, start: date, days: int) -> list[dict]:
    """Per date and slot: how many places are left for one officer."""
    out = []
    cap = settings.SLOT_CAPACITY_PER_OFFICER
    for i in range(days):
        day = start + timedelta(days=i)
        ds = day.isoformat()
        problem = date_problem(day)
        entry = {"date": ds, "bookable": problem is None, "reason": problem, "slots": []}
        for name in SLOTS:
            used = booked_count(applications_col, officer_id, ds, name) if problem is None else 0
            entry["slots"].append({
                "slot": name,
                "label": SLOTS[name]["label"],
                "booked": used,
                "capacity": cap,
                "available": max(0, cap - used) if problem is None else 0,
            })
        out.append(entry)
    return out


def history_entry(kind: str, day: str, slot: str, by, reason: Optional[str], previous: Optional[dict] = None) -> dict:
    """kind: scheduled | rescheduled | assigned | reassigned"""
    return {
        "kind": kind,
        "date": day,
        "slot": slot,
        "at": datetime.now(timezone.utc),
        "by": by,
        "reason": reason,
        "previous": previous,
    }
