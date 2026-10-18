"""Oversight views for administrators and officers (roadmap #8): pendency ageing, district-wise
position and the enforcement list of instruments whose certificate has lapsed.

Read-only, and the heavy aggregate reads may come from a replica (like dashboard.py: a monitoring view
can be a moment behind). The user records used for owner names are always read from the primary.
An admin sees the whole country; an LMO / GATC officer sees only their own jurisdiction
(the same `jurisdiction_filter` the application queue uses), and any state / district filter only
narrows that. An officer with no jurisdiction on file sees nothing. Owners have no access.
"""
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Query

from app.config.db import (
    applications_col,
    certificates_col,
    districts_col,
    instruments_col,
    read_replica,
    states_col,
    users_col,
)
from app.config.settings import ENFORCEMENT_MAX_SCAN, PENDENCY_TARGET_DAYS
from app.middleware.auth import jurisdiction_filter, role_required
from app.models.oversight import (
    DistrictReport,
    DistrictRow,
    EnforcementItem,
    EnforcementReport,
    EnforcementSummary,
    PendencyBucket,
    PendencyItem,
    PendencyReport,
    PendencyStatusCounts,
    ReverificationInfo,
)
from app.utils import search as search_utils

router = APIRouter(prefix="/api/v1/oversight", tags=["oversight"])

OPEN_STATUSES = ["submitted", "scheduled", "inspected"]
VERIFIED_STATUSES = ["certified", "expiring"]
# (label, min age in days, max age in days or None). An age of N means "N whole days since submitted".
AGE_BUCKETS = [
    ("0-7 days", 0, 7),
    ("8-14 days", 8, 14),
    ("15-30 days", 15, 30),
    ("31-60 days", 31, 60),
    ("Over 60 days", 61, None),
]
# Days since the certificate ran out: up to 30 recent, 31-90 overdue, beyond that long overdue.
RECENT_MAX_DAYS = 30
OVERDUE_MAX_DAYS = 90
ID_CHUNK = 1000

OfficerRole = Annotated[dict, Depends(role_required("admin", "lmo", "gatc"))]


# ---------------------------------------------------------------- helpers


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _naive(dt: datetime) -> datetime:
    """MongoDB stores UTC; build queries with naive UTC like the rest of the code base does."""
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _scope(user: dict) -> dict:
    """Who-may-see filter on application-shaped documents (state_code / district_code)."""
    if user["role"] == "admin":
        return {}
    if not user.get("jurisdiction"):
        return {"state_code": "__no_jurisdiction__"}  # fail closed rather than showing the country
    return jurisdiction_filter(user)


def _where(scope: dict, state_code: Optional[str], district_code: Optional[str], prefix: str = "", **extra) -> dict:
    """`scope` AND the user's filters AND `extra`. `prefix` re-targets the place keys, e.g. "location."."""
    clauses = [{prefix + k: v for k, v in scope.items()}] if scope else []
    if state_code:
        clauses.append({prefix + "state_code": state_code})
    if district_code:
        clauses.append({prefix + "district_code": district_code})
    clauses.extend({k: v} for k, v in extra.items())
    if not clauses:
        return {}
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def _place_names(pairs: set[tuple[str, str]]) -> tuple[dict, dict]:
    """({state_code: name}, {(state_code, district_code): name}) for the places in `pairs`."""
    state_codes = sorted({s for s, _ in pairs if s})
    district_codes = sorted({d for _, d in pairs if d})
    states = {
        s["code"]: s["name"]
        for s in read_replica(states_col).find({"code": {"$in": state_codes}}, {"code": 1, "name": 1})
    } if state_codes else {}
    districts = {
        (d["state_code"], d["code"]): d["name"]
        for d in read_replica(districts_col).find(
            {"state_code": {"$in": state_codes}, "code": {"$in": district_codes}}, {"state_code": 1, "code": 1, "name": 1}
        )
    } if district_codes else {}
    return states, districts


def _chunks(values: list, size: int = ID_CHUNK):
    for i in range(0, len(values), size):
        yield values[i:i + size]


# ---------------------------------------------------------------- pendency ageing


@router.get("/pendency", response_model=PendencyReport)
def pendency(
    current_user: OfficerRole,
    state_code: search_utils.StateCodeParam = None,
    district_code: search_utils.DistrictCodeParam = None,
):
    """Applications still open (submitted, scheduled or inspected), grouped by how long they have waited."""
    now = _utcnow()
    scope = _scope(current_user)
    apps = read_replica(applications_col)
    open_where = _where(scope, state_code, district_code, status={"$in": OPEN_STATUSES})

    buckets: list[PendencyBucket] = []
    totals = PendencyStatusCounts()
    for label, lo, hi in AGE_BUCKETS:
        age = {"$lte": _naive(now - timedelta(days=lo))}  # at least `lo` whole days old
        if hi is not None:
            age["$gt"] = _naive(now - timedelta(days=hi + 1))  # but not yet `hi + 1` days old
        by_status = PendencyStatusCounts()
        for row in apps.aggregate([
            {"$match": {"$and": [open_where, {"submitted_at": age}]}},
            {"$group": {"_id": "$status", "n": {"$sum": 1}}},
        ]):
            if row["_id"] in OPEN_STATUSES:
                setattr(by_status, row["_id"], row["n"])
                setattr(totals, row["_id"], getattr(totals, row["_id"]) + row["n"])
        buckets.append(PendencyBucket(
            label=label, min_days=lo, max_days=hi, count=sum(by_status.dict().values()), by_status=by_status,
        ))

    total_open = sum(b.count for b in buckets)
    unassigned = apps.count_documents({"$and": [open_where, {"assigned_officer_id": None}]})
    over_target = apps.count_documents(
        {"$and": [open_where, {"submitted_at": {"$lt": _naive(now - timedelta(days=PENDENCY_TARGET_DAYS))}}]}
    )

    oldest_docs = list(apps.find(open_where).sort("submitted_at", 1).limit(10))
    instruments = {
        i["_id"]: i
        for i in read_replica(instruments_col).find(
            {"_id": {"$in": [d["instrument_id"] for d in oldest_docs]}}, {"uiid": 1, "type": 1}
        )
    } if oldest_docs else {}
    states, districts = _place_names({(d.get("state_code"), d.get("district_code")) for d in oldest_docs})
    oldest = []
    for d in oldest_docs:
        inst = instruments.get(d["instrument_id"], {})
        submitted = _aware(d["submitted_at"])
        oldest.append(PendencyItem(
            application_id=str(d["_id"]),
            uiid=inst.get("uiid"),
            instrument_type=inst.get("type"),
            status=d["status"],
            application_type=d.get("application_type", "initial"),
            state_name=states.get(d.get("state_code")),
            district_name=districts.get((d.get("state_code"), d.get("district_code"))),
            submitted_at=submitted.isoformat(),
            age_days=max((now - submitted).days, 0),
            assigned=d.get("assigned_officer_id") is not None,
        ))

    return PendencyReport(
        generated_at=now.isoformat(), target_days=PENDENCY_TARGET_DAYS, total_open=total_open,
        unassigned=unassigned, over_target=over_target, by_status=totals, buckets=buckets, oldest=oldest,
    )


# ---------------------------------------------------------------- district-wise


@router.get("/districts", response_model=DistrictReport)
def districts_report(
    current_user: OfficerRole,
    state_code: search_utils.StateCodeParam = None,
    district_code: search_utils.DistrictCodeParam = None,
):
    """One row per district: instruments registered, applications open / overdue, verified, expired."""
    now = _utcnow()
    scope = _scope(current_user)
    place = {"s": "$state_code", "d": "$district_code"}
    rows: dict[tuple[str, str], dict] = {}

    def row(s, d) -> dict:
        return rows.setdefault((s or "unknown", d or "unknown"), {
            "instruments": 0, "open_applications": 0, "overdue_applications": 0, "verified": 0, "expired": 0,
        })

    apps = read_replica(applications_col)
    for r in apps.aggregate([
        {"$match": _where(scope, state_code, district_code) or {}},
        {"$group": {"_id": {**place, "st": "$status"}, "n": {"$sum": 1}}},
    ]):
        status, target = r["_id"]["st"], row(r["_id"]["s"], r["_id"]["d"])
        if status in OPEN_STATUSES:
            target["open_applications"] += r["n"]
        elif status in VERIFIED_STATUSES:
            target["verified"] += r["n"]
        elif status == "expired":
            target["expired"] += r["n"]

    overdue_cutoff = _naive(now - timedelta(days=PENDENCY_TARGET_DAYS))
    for r in apps.aggregate([
        {"$match": _where(scope, state_code, district_code, status={"$in": OPEN_STATUSES}, submitted_at={"$lt": overdue_cutoff})},
        {"$group": {"_id": place, "n": {"$sum": 1}}},
    ]):
        row(r["_id"]["s"], r["_id"]["d"])["overdue_applications"] += r["n"]

    for r in read_replica(instruments_col).aggregate([
        {"$match": _where(scope, state_code, district_code, prefix="location.") or {}},
        {"$group": {"_id": {"s": "$location.state_code", "d": "$location.district_code"}, "n": {"$sum": 1}}},
    ]):
        row(r["_id"]["s"], r["_id"]["d"])["instruments"] += r["n"]

    states, districts = _place_names(set(rows))
    out = [
        DistrictRow(
            state_code=s, state_name=states.get(s, "Unspecified"),
            district_code=d, district_name=districts.get((s, d), "Unspecified"), **vals,
        )
        for (s, d), vals in rows.items()
    ]
    out.sort(key=lambda r: (-r.overdue_applications, -r.open_applications, r.state_name, r.district_name))
    totals = {k: sum(getattr(r, k) for r in out) for k in
              ("instruments", "open_applications", "overdue_applications", "verified", "expired")}
    return DistrictReport(generated_at=now.isoformat(), target_days=PENDENCY_TARGET_DAYS, totals=totals, rows=out)


# ---------------------------------------------------------------- enforcement


def _band(days_overdue: int) -> str:
    if days_overdue <= RECENT_MAX_DAYS:
        return "recent"
    return "overdue" if days_overdue <= OVERDUE_MAX_DAYS else "long_overdue"


@router.get("/enforcement", response_model=EnforcementReport)
def enforcement(
    current_user: OfficerRole,
    state_code: search_utils.StateCodeParam = None,
    district_code: search_utils.DistrictCodeParam = None,
    reverification: Optional[Literal["applied", "none"]] = None,
    min_days_overdue: Annotated[int, Query(ge=0, le=36500)] = 0,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
):
    """Instruments whose newest certificate has run out, most overdue first.

    An instrument that already has a newer valid certificate is not listed. One whose owner has an open
    re-verification application is listed but marked `reverification` (a mitigating status, not an excuse:
    the certificate is still not in force). Instruments that were never certified are not covered.
    """
    now = _utcnow()
    scope = _scope(current_user)

    # 1. Expired applications in scope, newest first (the expiry job moves them to "expired").
    found = list(
        read_replica(applications_col)
        .find(_where(scope, state_code, district_code, status="expired"),
              {"instrument_id": 1, "state_code": 1, "district_code": 1})
        .sort("submitted_at", -1)
        .limit(ENFORCEMENT_MAX_SCAN + 1)
    )
    truncated = len(found) > ENFORCEMENT_MAX_SCAN
    place_of = {d["instrument_id"]: (d.get("state_code"), d.get("district_code")) for d in reversed(found[:ENFORCEMENT_MAX_SCAN])}
    instrument_ids = list(place_of)

    # 2. Newest certificate per instrument; lapsed only if even that one has run out.
    newest: dict = {}
    for chunk in _chunks(instrument_ids):
        for c in read_replica(certificates_col).find(
            {"instrument_id": {"$in": chunk}}, {"instrument_id": 1, "valid_until": 1, "cert_no": 1}
        ):
            if c.get("valid_until") is None:
                continue
            cur = newest.get(c["instrument_id"])
            if cur is None or _aware(c["valid_until"]) > _aware(cur["valid_until"]):
                newest[c["instrument_id"]] = c
    lapsed = {i: c for i, c in newest.items() if _aware(c["valid_until"]) < now}

    # 3. Open re-verification applications for those instruments (earliest one counts).
    applied: dict = {}
    for chunk in _chunks(list(lapsed)):
        for a in apps_open(chunk):
            cur = applied.get(a["instrument_id"])
            if cur is None or _aware(a["submitted_at"]) < _aware(cur["submitted_at"]):
                applied[a["instrument_id"]] = a

    entries = []
    for iid, cert in lapsed.items():
        days = max((now - _aware(cert["valid_until"])).days, 0)
        if days < min_days_overdue:
            continue
        has_applied = iid in applied
        if (reverification == "applied" and not has_applied) or (reverification == "none" and has_applied):
            continue
        entries.append((iid, cert, days, applied.get(iid)))
    entries.sort(key=lambda e: (-e[2], str(e[0])))

    bands = [_band(e[2]) for e in entries]
    summary = EnforcementSummary(
        lapsed=len(entries),
        reverification_applied=sum(1 for e in entries if e[3]),
        no_reverification=sum(1 for e in entries if not e[3]),
        recent=bands.count("recent"), overdue=bands.count("overdue"), long_overdue=bands.count("long_overdue"),
    )

    # 4. Names only for the rows on this page.
    start = (page - 1) * page_size
    window = entries[start:start + page_size]
    instruments = {
        i["_id"]: i
        for i in read_replica(instruments_col).find(
            {"_id": {"$in": [e[0] for e in window]}}, {"uiid": 1, "type": 1, "owner_id": 1, "location.address_line": 1}
        )
    } if window else {}
    owners = {
        u["_id"]: u
        for u in users_col.find(
            {"_id": {"$in": [i.get("owner_id") for i in instruments.values()]}}, {"name": 1, "org_name": 1}
        )
    } if instruments else {}
    states, districts = _place_names({place_of[e[0]] for e in window})

    items = []
    for iid, cert, days, app in window:
        inst = instruments.get(iid, {})
        owner = owners.get(inst.get("owner_id"), {})
        s, d = place_of[iid]
        items.append(EnforcementItem(
            instrument_id=str(iid), uiid=inst.get("uiid"), instrument_type=inst.get("type"),
            owner_name=owner.get("name"), org_name=owner.get("org_name"),
            address_line=(inst.get("location") or {}).get("address_line"),
            state_code=s or "unknown", state_name=states.get(s), district_code=d or "unknown",
            district_name=districts.get((s, d)),
            cert_no=cert.get("cert_no"), valid_until=_aware(cert["valid_until"]).isoformat(),
            days_overdue=days, band=_band(days),
            reverification=ReverificationInfo(status=app["status"], applied_on=_aware(app["submitted_at"]).isoformat()) if app else None,
        ))

    return EnforcementReport(
        generated_at=now.isoformat(), summary=summary, total=len(entries), page=page, page_size=page_size,
        truncated=truncated, items=items,
    )


def apps_open(instrument_ids: list):
    return read_replica(applications_col).find(
        {"instrument_id": {"$in": instrument_ids}, "status": {"$in": OPEN_STATUSES}}, {"instrument_id": 1, "status": 1, "submitted_at": 1}
    )
