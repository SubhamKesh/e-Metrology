"""Enforcement cases: the record kept for an instrument with no valid certificate (lapsed or never certified).

A case is opened by an officer from the Oversight lists. It holds a timeline (opened, notices sent to the
owner, notes, escalations, resolution). One active case per instrument.

  status   open -> notice_sent -> escalated -> resolved       (escalated goes back to notice_sent on a new notice)
  level    lmo -> gatc -> admin                               (who holds the case; only they, or an admin, may act)

A case resolves itself when the instrument gets a valid certificate ("renewed" / "certified"); an officer can
also close it with a reason. Once `ESCALATION_AFTER_DAYS` India calendar days pass after the last notice with
no resolution, the hourly job escalates it one level (officers can escalate by hand at any time).
Nothing here fines or blocks anyone: it is a record plus a notice, the decision stays with the officers.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from pymongo import ReturnDocument

from app.config.db import certificates_col, enforcement_cases_col
from app.config.settings import ESCALATION_AFTER_DAYS, NEVER_CERTIFIED_GRACE_DAYS
from app.services import audit as audit_service

logger = logging.getLogger("maapsetu")

LEVELS = ["lmo", "gatc", "admin"]
ROLE_TITLE = {"lmo": "Legal Metrology Officer", "gatc": "GATC", "admin": "Admin"}
IST = timezone(timedelta(hours=5, minutes=30))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def naive(dt: datetime) -> datetime:
    """MongoDB stores UTC; queries use naive UTC like the rest of the code base."""
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def ist_day_start(now: datetime) -> datetime:
    local = now.astimezone(IST)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def calendar_days(then: datetime, now: datetime) -> int:
    return max((now.astimezone(IST).date() - aware(then).astimezone(IST).date()).days, 0)


def next_level(level: str) -> Optional[str]:
    i = LEVELS.index(level) if level in LEVELS else len(LEVELS) - 1
    return LEVELS[i + 1] if i + 1 < len(LEVELS) else None


# ---------------------------------------------------------------- is the instrument still on the list?


def newest_certificate(instrument_id) -> Optional[dict]:
    return certificates_col.find_one(
        {"instrument_id": instrument_id, "valid_until": {"$ne": None}}, sort=[("valid_until", -1)]
    )


def classify(instrument: dict, now: datetime) -> Optional[str]:
    """'lapsed', 'never_certified', or None when the instrument is not (or not yet) an enforcement matter."""
    cert = newest_certificate(instrument["_id"])
    if cert is not None:
        return "lapsed" if aware(cert["valid_until"]) < now else None
    if certificates_col.find_one({"instrument_id": instrument["_id"]}, {"_id": 1}) is not None:
        return None  # a certificate exists but carries no expiry date: not ours to judge
    registered = instrument["_id"].generation_time
    return "never_certified" if calendar_days(registered, now) > NEVER_CERTIFIED_GRACE_DAYS else None


def _resolution_for(case: dict, now: datetime) -> Optional[str]:
    cert = newest_certificate(case["instrument_id"])
    if case["kind"] == "lapsed":
        return "renewed" if cert is not None and aware(cert["valid_until"]) >= now else None
    return "certified" if certificates_col.find_one({"instrument_id": case["instrument_id"]}, {"_id": 1}) else None


# ---------------------------------------------------------------- changing a case


def event(action: str, *, by: Optional[dict] = None, text: Optional[str] = None, to_level: Optional[str] = None,
          emailed: Optional[bool] = None, at: Optional[datetime] = None) -> dict:
    return {
        "at": at or now_utc(), "action": action,
        "by_id": by["_id"] if by else None,
        "by_name": (by.get("name") or by.get("email")) if by else None,
        "by_role": by.get("role") if by else None,
        "text": text or None, "to_level": to_level, "emailed": emailed,
    }


def sync_case(case: dict, now: Optional[datetime] = None) -> dict:
    """Resolve the case if the instrument now has a valid certificate. Returns the current document."""
    if not case.get("active"):
        return case
    now = now or now_utc()
    reason = _resolution_for(case, now)
    if reason is None:
        return case
    text = "Certificate renewed" if reason == "renewed" else "Instrument verified and certified"
    updated = enforcement_cases_col.find_one_and_update(
        {"_id": case["_id"], "active": True},
        {
            "$set": {"status": "resolved", "active": False, "resolved_at": now, "resolution": reason, "updated_at": now},
            "$push": {"events": event("resolved", text=text, at=now)},
        },
        return_document=ReturnDocument.AFTER,
    )
    return updated or enforcement_cases_col.find_one({"_id": case["_id"]}) or case


def escalate_case(case: dict, *, by: Optional[dict], reason: Optional[str]) -> Optional[dict]:
    """Move an active case up one level. Returns the updated case, or None if it cannot move
    (already with the admin, no longer active, or changed by someone else a moment ago)."""
    target = next_level(case["level"])
    if target is None or not case.get("active"):
        return None
    now = now_utc()
    updated = enforcement_cases_col.find_one_and_update(
        {"_id": case["_id"], "active": True, "level": case["level"]},
        {
            "$set": {"level": target, "status": "escalated", "escalated_at": now, "updated_at": now},
            "$push": {"events": event("escalated", by=by, text=reason, to_level=target, at=now)},
        },
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        return None
    audit_service.log_event(
        "enforcement_case_escalated", outcome="success",
        email=(by or {}).get("email"), user_id=str(by["_id"]) if by else None, role=(by or {}).get("role"),
        detail=f"case={case['_id']} to={target}{' auto' if by is None else ''}",
    )
    return updated


def due_for_escalation_filter(now: datetime) -> dict:
    """Cases whose last notice is at least ESCALATION_AFTER_DAYS India calendar days old and that can still go up."""
    cutoff = ist_day_start(now) - timedelta(days=ESCALATION_AFTER_DAYS - 1)
    return {
        "active": True, "status": "notice_sent", "level": {"$ne": "admin"},
        "last_notice_at": {"$lt": naive(cutoff)},
    }


def run_maintenance(now: Optional[datetime] = None) -> dict:
    """Hourly: resolve cases whose instrument got a certificate, then escalate cases left unanswered."""
    now = now or now_utc()
    resolved = escalated = 0
    for case in list(enforcement_cases_col.find({"active": True})):
        if not sync_case(case, now).get("active"):
            resolved += 1
    for case in list(enforcement_cases_col.find(due_for_escalation_filter(now))):
        if escalate_case(case, by=None, reason=f"No resolution {ESCALATION_AFTER_DAYS} days after the last notice") is not None:
            escalated += 1
    return {"resolved": resolved, "escalated": escalated}
