"""Read-only view of the security audit trail (admin only).

The trail itself is written by app/services/audit.py. This router only reads
it: there is deliberately no endpoint anywhere that edits or deletes an audit
record. Records leave the system only when MongoDB expires them after
AUDIT_LOG_RETENTION_DAYS.
"""
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config.db import read_replica
from app.middleware.auth import role_required
from app.models.audit import AuditLogOut, AuditLogPage
from app.services import audit as audit_service

router = APIRouter(prefix="/api/v1/admin/audit-logs", tags=["admin-audit"])


def _to_out(doc: dict) -> AuditLogOut:
    created_at = doc["created_at"]
    if created_at.tzinfo is None:  # MongoDB hands back UTC datetimes without a tzinfo
        created_at = created_at.replace(tzinfo=timezone.utc)
    return AuditLogOut(
        id=str(doc["_id"]),
        event=doc.get("event", ""),
        outcome=doc.get("outcome", ""),
        email=doc.get("email"),
        user_id=doc.get("user_id"),
        role=doc.get("role"),
        actor_id=doc.get("actor_id"),
        actor_email=doc.get("actor_email"),
        ip=doc.get("ip"),
        user_agent=doc.get("user_agent"),
        detail=doc.get("detail"),
        created_at=created_at,
    )


@router.get("", response_model=AuditLogPage)
def list_audit_logs(
    event: Optional[str] = Query(None, max_length=64, description="Exact event name"),
    outcome: Optional[Literal["success", "failure", "blocked", "ignored"]] = None,
    role: Optional[Literal["owner", "lmo", "gatc", "admin"]] = None,
    search: Optional[str] = Query(
        None, max_length=100, description="Part of the account's or the acting admin's email (case-insensitive)"
    ),
    date_from: Optional[date] = Query(None, description="First day to include (UTC)"),
    date_to: Optional[date] = Query(None, description="Last day to include (UTC)"),
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(role_required("admin")),
):
    """Newest first. All filters are optional and combine with AND."""
    if event is not None and event not in audit_service.KNOWN_AUDIT_EVENTS:
        raise HTTPException(status_code=400, detail="Unknown event name.")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="'From' date must not be after 'To' date.")

    query: dict = {}
    if event:
        query["event"] = event
    if outcome:
        query["outcome"] = outcome
    if role:
        query["role"] = role
    if search and search.strip():
        # re.escape: the text is matched literally, never interpreted as a pattern.
        pattern = {"$regex": re.escape(search.strip()), "$options": "i"}
        query["$or"] = [{"email": pattern}, {"actor_email": pattern}]
    if date_from or date_to:
        window: dict = {}
        if date_from:
            window["$gte"] = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        if date_to:
            window["$lt"] = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
        query["created_at"] = window

    # An audit view is the textbook staleness-tolerant read: use a replica when configured.
    collection = read_replica(audit_service.audit_logs_col)
    total = collection.count_documents(query)
    docs = (
        collection.find(query)
        .sort([("created_at", -1), ("_id", -1)])
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    return AuditLogPage(
        items=[_to_out(d) for d in docs],
        total=total,
        page=page,
        page_size=page_size,
        events=list(audit_service.KNOWN_AUDIT_EVENTS),
    )
