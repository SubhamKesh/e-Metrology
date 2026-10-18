"""Oversight views for administrators and officers (roadmap #8): pendency ageing, district-wise
position and the enforcement list of instruments whose certificate has lapsed.

Read-only (the CSV / PDF exports live in routers/reports.py and call the builders in this module), and the heavy aggregate reads may come from a replica (like dashboard.py: a monitoring view
can be a moment behind). The user records used for owner names are always read from the primary.
An admin sees the whole country; an LMO / GATC officer sees only their own jurisdiction
(the same `jurisdiction_filter` the application queue uses), and any state / district filter only
narrows that. An officer with no jurisdiction on file sees nothing. Owners have no access.
"""
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Query

from app.config.db import (
    applications_col,
    certificates_col,
    districts_col,
    enforcement_cases_col,
    instruments_col,
    read_replica,
    states_col,
    users_col,
)
from app.config.settings import ENFORCEMENT_MAX_SCAN, NEVER_CERTIFIED_GRACE_DAYS, PENDENCY_TARGET_DAYS
from app.middleware.auth import jurisdiction_filter, role_required
from app.models.oversight import (
    CaseRef,
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
    UncertifiedItem,
    UncertifiedReport,
    UncertifiedSummary,
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


IST = timezone(timedelta(hours=5, minutes=30))


def _ist_day_start(now: datetime) -> datetime:
    """Midnight (India time) that began today's India date, as an aware UTC instant."""
    local = now.astimezone(IST)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def _calendar_days(then: datetime, now: datetime) -> int:
    """Whole India calendar days from `then` to `now` (same India date = 0, never negative)."""
    return max((now.astimezone(IST).date() - _aware(then).astimezone(IST).date()).days, 0)


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


def case_refs(instrument_ids: list) -> dict:
    """{instrument_id: CaseRef} for instruments that have an open case. Read from the primary: an officer who
    has just opened a case must see it on the very next refresh."""
    refs: dict = {}
    for chunk in _chunks(list(instrument_ids)):
        for c in enforcement_cases_col.find(
            {"instrument_id": {"$in": chunk}, "active": True}, {"instrument_id": 1, "status": 1, "level": 1}
        ):
            refs[c["instrument_id"]] = CaseRef(id=str(c["_id"]), status=c["status"], level=c["level"])
    return refs


def _chunks(values: list, size: int = ID_CHUNK):
    for i in range(0, len(values), size):
        yield values[i:i + size]


# ---------------------------------------------------------------- pendency ageing


def pendency_items(docs: list[dict], now: datetime) -> list[PendencyItem]:
    """Application documents -> rows with the instrument's UIID / type and the place names."""
    instruments = {
        i["_id"]: i
        for i in read_replica(instruments_col).find(
            {"_id": {"$in": [d["instrument_id"] for d in docs]}}, {"uiid": 1, "type": 1}
        )
    } if docs else {}
    states, districts = _place_names({(d.get("state_code"), d.get("district_code")) for d in docs})
    items = []
    for d in docs:
        inst = instruments.get(d["instrument_id"], {})
        submitted = _aware(d["submitted_at"])
        items.append(PendencyItem(
            application_id=str(d["_id"]),
            uiid=inst.get("uiid"),
            instrument_type=inst.get("type"),
            status=d["status"],
            application_type=d.get("application_type", "initial"),
            state_name=states.get(d.get("state_code")),
            district_name=districts.get((d.get("state_code"), d.get("district_code"))),
            submitted_at=submitted.isoformat(),
            age_days=_calendar_days(submitted, now),
            assigned=d.get("assigned_officer_id") is not None,
        ))
    return items


def open_applications(user: dict, state_code: Optional[str], district_code: Optional[str], limit: int):
    """(rows, total) for the pendency export: every open application, longest waiting first, at most `limit`."""
    now = _utcnow()
    open_where = _where(_scope(user), state_code, district_code, status={"$in": OPEN_STATUSES})
    apps = read_replica(applications_col)
    docs = list(apps.find(open_where).sort("submitted_at", 1).limit(limit))
    return pendency_items(docs, now), apps.count_documents(open_where)


@router.get("/pendency", response_model=PendencyReport)
def pendency(
    current_user: OfficerRole,
    state_code: search_utils.StateCodeParam = None,
    district_code: search_utils.DistrictCodeParam = None,
):
    """Applications still open (submitted, scheduled or inspected), grouped by how long they have waited."""
    now = _utcnow()
    today = _ist_day_start(now)
    scope = _scope(current_user)
    apps = read_replica(applications_col)
    open_where = _where(scope, state_code, district_code, status={"$in": OPEN_STATUSES})

    buckets: list[PendencyBucket] = []
    totals = PendencyStatusCounts()
    for label, lo, hi in AGE_BUCKETS:
        # Ages are India calendar days: 0 = submitted today (IST), 1 = yesterday, and so on.
        age = {"$lt": _naive(today - timedelta(days=lo - 1))}  # at least `lo` days old
        if hi is not None:
            age["$gte"] = _naive(today - timedelta(days=hi))  # at most `hi` days old
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
        {"$and": [open_where, {"submitted_at": {"$lt": _naive(today - timedelta(days=PENDENCY_TARGET_DAYS))}}]}
    )

    oldest = pendency_items(list(apps.find(open_where).sort("submitted_at", 1).limit(10)), now)

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

    overdue_cutoff = _naive(_ist_day_start(now) - timedelta(days=PENDENCY_TARGET_DAYS))
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


def _lapsed_instruments(scope: dict, state_code: Optional[str], district_code: Optional[str], now: datetime):
    """Instruments whose newest certificate has run out, most overdue first, inside the caller's scope.

    Worked out from the certificates themselves (an instrument's latest `valid_until` is in the past), so
    it does not wait for the hourly expiry job to flip an application to `expired`, and it is not cut short
    by a scan of applications. The place comes from the instrument's registered location.
    Returns ([(instrument_id, valid_until, (state_code, district_code))], truncated). Only if more than
    ENFORCEMENT_MAX_SCAN instruments are lapsed in scope does it stop, keeping the most overdue.
    """
    newest = [
        r for r in read_replica(certificates_col).aggregate([
            {"$match": {"valid_until": {"$ne": None}, "instrument_id": {"$ne": None}}},
            {"$group": {"_id": "$instrument_id", "valid_until": {"$max": "$valid_until"}}},
            {"$match": {"valid_until": {"$lt": _naive(now)}}},
        ])
    ]
    newest.sort(key=lambda r: (_aware(r["valid_until"]), str(r["_id"])))  # oldest expiry = most overdue first

    place_where = _where(scope, state_code, district_code, prefix="location.")
    out: list = []
    truncated = False
    for chunk in _chunks(newest):
        until = {r["_id"]: r["valid_until"] for r in chunk}
        query = {"_id": {"$in": list(until)}}
        found = {
            i["_id"]: i.get("location") or {}
            for i in read_replica(instruments_col).find(
                {"$and": [query, place_where]} if place_where else query, {"location.state_code": 1, "location.district_code": 1}
            )
        }
        for r in chunk:  # keep the chunk's own order
            if r["_id"] in found:
                loc = found[r["_id"]]
                out.append((r["_id"], _aware(r["valid_until"]), (loc.get("state_code"), loc.get("district_code"))))
        if len(out) > ENFORCEMENT_MAX_SCAN:
            truncated = True
            out = out[:ENFORCEMENT_MAX_SCAN]
            break
    return out, truncated


class EnforcementResult:
    """The filtered enforcement list plus the summary over every match."""

    def __init__(self, now, entries, summary, truncated):
        self.now, self.entries, self.summary, self.truncated = now, entries, summary, truncated


def build_enforcement(
    user: dict,
    state_code: Optional[str] = None,
    district_code: Optional[str] = None,
    reverification: Optional[str] = None,
    min_days_overdue: int = 0,
) -> EnforcementResult:
    now = _utcnow()
    lapsed, truncated = _lapsed_instruments(_scope(user), state_code, district_code, now)

    # Open re-verification applications for those instruments (the earliest one counts).
    applied: dict = {}
    for chunk in _chunks([e[0] for e in lapsed]):
        for a in apps_open(chunk):
            cur = applied.get(a["instrument_id"])
            if cur is None or _aware(a["submitted_at"]) < _aware(cur["submitted_at"]):
                applied[a["instrument_id"]] = a

    entries = []  # (instrument_id, valid_until, days overdue, open application or None, place)
    for iid, valid_until, place in lapsed:
        days = _calendar_days(valid_until, now)
        if days < min_days_overdue:
            continue
        has_applied = iid in applied
        if (reverification == "applied" and not has_applied) or (reverification == "none" and has_applied):
            continue
        entries.append((iid, valid_until, days, applied.get(iid), place))
    entries.sort(key=lambda e: (-e[2], str(e[0])))

    bands = [_band(e[2]) for e in entries]
    summary = EnforcementSummary(
        lapsed=len(entries),
        reverification_applied=sum(1 for e in entries if e[3]),
        no_reverification=sum(1 for e in entries if not e[3]),
        recent=bands.count("recent"), overdue=bands.count("overdue"), long_overdue=bands.count("long_overdue"),
    )
    return EnforcementResult(now, entries, summary, truncated)


def enforcement_items(window: list) -> list[EnforcementItem]:
    """Names, certificate numbers and owner for the given entries only (a page, or an export)."""
    if not window:
        return []
    instruments = {}
    for chunk in _chunks([e[0] for e in window]):
        for i in read_replica(instruments_col).find(
            {"_id": {"$in": chunk}}, {"uiid": 1, "type": 1, "owner_id": 1, "location.address_line": 1}
        ):
            instruments[i["_id"]] = i
    owners = {}
    owner_ids = list({i.get("owner_id") for i in instruments.values() if i.get("owner_id")})
    for chunk in _chunks(owner_ids):
        for u in users_col.find({"_id": {"$in": chunk}}, {"name": 1, "org_name": 1}):  # primary, never a replica
            owners[u["_id"]] = u
    # The certificate that ran out last, for its number.
    cert_no: dict = {}
    for chunk in _chunks([e[0] for e in window]):
        for c in read_replica(certificates_col).find({"instrument_id": {"$in": chunk}}, {"instrument_id": 1, "valid_until": 1, "cert_no": 1}):
            if c.get("valid_until") is None:
                continue
            cur = cert_no.get(c["instrument_id"])
            if cur is None or _aware(c["valid_until"]) > cur[0]:
                cert_no[c["instrument_id"]] = (_aware(c["valid_until"]), c.get("cert_no"))
    states, districts = _place_names({e[4] for e in window})
    refs = case_refs([e[0] for e in window])

    items = []
    for iid, valid_until, days, app, (s, d) in window:
        inst = instruments.get(iid, {})
        owner = owners.get(inst.get("owner_id"), {})
        items.append(EnforcementItem(
            instrument_id=str(iid), uiid=inst.get("uiid"), instrument_type=inst.get("type"),
            owner_name=owner.get("name"), org_name=owner.get("org_name"),
            address_line=(inst.get("location") or {}).get("address_line"),
            state_code=s or "unknown", state_name=states.get(s), district_code=d or "unknown",
            district_name=districts.get((s, d)),
            cert_no=(cert_no.get(iid) or (None, None))[1], valid_until=valid_until.isoformat(),
            days_overdue=days, band=_band(days),
            reverification=ReverificationInfo(status=app["status"], applied_on=_aware(app["submitted_at"]).isoformat()) if app else None,
            case=refs.get(iid),
        ))
    return items


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

    Based on the certificates' own expiry dates. An instrument that already has a newer valid certificate is
    not listed. One whose owner has an open re-verification application is listed but marked
    `reverification` (a mitigating status, not an excuse: the certificate is still not in force).
    Instruments that were never certified are not covered.
    """
    result = build_enforcement(current_user, state_code, district_code, reverification, min_days_overdue)
    start = (page - 1) * page_size
    return EnforcementReport(
        generated_at=result.now.isoformat(), summary=result.summary, total=len(result.entries), page=page,
        page_size=page_size, truncated=result.truncated,
        items=enforcement_items(result.entries[start:start + page_size]),
    )


def apps_open(instrument_ids: list):
    return read_replica(applications_col).find(
        {"instrument_id": {"$in": instrument_ids}, "status": {"$in": OPEN_STATUSES}}, {"instrument_id": 1, "status": 1, "submitted_at": 1}
    )


# ---------------------------------------------------------------- never certified


def registered_at(instrument_id: ObjectId) -> datetime:
    """When an instrument was registered. Instruments carry no date field, but their ObjectId holds the
    moment they were created, so this works for every instrument already in the database."""
    return instrument_id.generation_time


def _never_certified_instruments(scope: dict, state_code: Optional[str], district_code: Optional[str], now: datetime):
    """Instruments registered more than NEVER_CERTIFIED_GRACE_DAYS India calendar days ago that have no
    certificate at all, oldest registration first, inside the caller's scope.
    Returns ([instrument documents], truncated)."""
    cutoff = ObjectId.from_datetime(_naive(_ist_day_start(now) - timedelta(days=NEVER_CERTIFIED_GRACE_DAYS)))
    place_where = _where(scope, state_code, district_code, prefix="location.")
    match: dict = {"_id": {"$lt": cutoff}}
    if place_where:
        match = {"$and": [match, place_where]}
    docs = list(read_replica(instruments_col).aggregate([
        {"$match": match},
        {"$lookup": {"from": certificates_col.name, "localField": "_id", "foreignField": "instrument_id", "as": "certs"}},
        {"$match": {"certs": {"$size": 0}}},
        {"$project": {"uiid": 1, "type": 1, "owner_id": 1, "location": 1}},
        {"$sort": {"_id": 1}},
        {"$limit": ENFORCEMENT_MAX_SCAN + 1},
    ]))
    truncated = len(docs) > ENFORCEMENT_MAX_SCAN
    return docs[:ENFORCEMENT_MAX_SCAN], truncated


class UncertifiedResult:
    def __init__(self, now, entries, summary, truncated):
        self.now, self.entries, self.summary, self.truncated = now, entries, summary, truncated


def build_uncertified(
    user: dict,
    state_code: Optional[str] = None,
    district_code: Optional[str] = None,
    application: Optional[str] = None,
    min_days: int = 0,
) -> UncertifiedResult:
    now = _utcnow()
    docs, truncated = _never_certified_instruments(_scope(user), state_code, district_code, now)
    applied: dict = {}
    for chunk in _chunks([d["_id"] for d in docs]):
        for a in apps_open(chunk):
            cur = applied.get(a["instrument_id"])
            if cur is None or _aware(a["submitted_at"]) < _aware(cur["submitted_at"]):
                applied[a["instrument_id"]] = a

    entries = []  # (instrument doc, days since registered, open application or None)
    for d in docs:
        days = _calendar_days(registered_at(d["_id"]), now)
        if days < min_days:
            continue
        has_applied = d["_id"] in applied
        if (application == "applied" and not has_applied) or (application == "none" and has_applied):
            continue
        entries.append((d, days, applied.get(d["_id"])))
    entries.sort(key=lambda e: (-e[1], str(e[0]["_id"])))
    summary = UncertifiedSummary(
        total=len(entries),
        applied=sum(1 for e in entries if e[2]),
        not_applied=sum(1 for e in entries if not e[2]),
    )
    return UncertifiedResult(now, entries, summary, truncated)


def uncertified_items(window: list) -> list[UncertifiedItem]:
    if not window:
        return []
    owners = {}
    owner_ids = list({e[0].get("owner_id") for e in window if e[0].get("owner_id")})
    for chunk in _chunks(owner_ids):
        for u in users_col.find({"_id": {"$in": chunk}}, {"name": 1, "org_name": 1}):  # primary, never a replica
            owners[u["_id"]] = u
    places = {((e[0].get("location") or {}).get("state_code"), (e[0].get("location") or {}).get("district_code")) for e in window}
    states, districts = _place_names(places)
    refs = case_refs([e[0]["_id"] for e in window])
    items = []
    for d, days, app in window:
        loc = d.get("location") or {}
        s, dc = loc.get("state_code"), loc.get("district_code")
        owner = owners.get(d.get("owner_id"), {})
        items.append(UncertifiedItem(
            instrument_id=str(d["_id"]), uiid=d.get("uiid"), instrument_type=d.get("type"),
            owner_name=owner.get("name"), org_name=owner.get("org_name"), address_line=loc.get("address_line"),
            state_code=s or "unknown", state_name=states.get(s), district_code=dc or "unknown",
            district_name=districts.get((s, dc)),
            registered_on=registered_at(d["_id"]).isoformat(), days_since_registered=days,
            application=ReverificationInfo(status=app["status"], applied_on=_aware(app["submitted_at"]).isoformat()) if app else None,
            case=refs.get(d["_id"]),
        ))
    return items


@router.get("/uncertified", response_model=UncertifiedReport)
def uncertified(
    current_user: OfficerRole,
    state_code: search_utils.StateCodeParam = None,
    district_code: search_utils.DistrictCodeParam = None,
    application: Optional[Literal["applied", "none"]] = None,
    min_days: Annotated[int, Query(ge=0, le=36500)] = 0,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
):
    """Instruments registered more than `NEVER_CERTIFIED_GRACE_DAYS` days ago that have never had a
    certificate, longest registered first. An owner with an open application is listed but marked
    (a mitigating note: the instrument is still not verified)."""
    result = build_uncertified(current_user, state_code, district_code, application, min_days)
    start = (page - 1) * page_size
    return UncertifiedReport(
        generated_at=result.now.isoformat(), grace_days=NEVER_CERTIFIED_GRACE_DAYS, summary=result.summary,
        total=len(result.entries), page=page, page_size=page_size, truncated=result.truncated,
        items=uncertified_items(result.entries[start:start + page_size]),
    )
