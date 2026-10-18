"""#8 Oversight views: pendency ageing, district-wise position and the enforcement list.

Covers the numbers (ageing buckets, per-district counts, lapsed certificates, mitigating re-verification),
the filters, and above all who may see what: owners are refused, officers only see their jurisdiction.
"""
import os
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

from app.utils.security import create_access_token

BASE = "/api/v1/oversight"


def _ago(days=0, hours=0) -> datetime:
    """Naive UTC, which is what MongoDB hands back."""
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days, hours=hours)


def _ist_noon(days_ago: int) -> datetime:
    """Noon India time, `days_ago` India calendar days back, as naive UTC (so the age is exactly that)."""
    from app.routers.oversight import IST

    noon = datetime.now(timezone.utc).astimezone(IST).replace(hour=12, minute=0, second=0, microsecond=0)
    return (noon - timedelta(days=days_ago)).astimezone(timezone.utc).replace(tzinfo=None)


def _ist_midnight() -> datetime:
    """The start of today's India date, as naive UTC."""
    from app.routers.oversight import IST

    start = datetime.now(timezone.utc).astimezone(IST).replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def world(client, monkeypatch):
    import app.config.db as dbmod
    import app.routers.enforcement_cases as cases_router
    import app.routers.oversight as mod
    import app.services.enforcement_cases as cases_service

    db = dbmod.db
    for name in ["applications_col", "instruments_col", "certificates_col", "users_col", "states_col", "districts_col", "enforcement_cases_col"]:
        monkeypatch.setattr(mod, name, db[name.removesuffix("_col")])
    for name in ["enforcement_cases_col", "instruments_col", "users_col"]:
        monkeypatch.setattr(cases_router, name, db[name.removesuffix("_col")])
    for name in ["enforcement_cases_col", "certificates_col"]:
        monkeypatch.setattr(cases_service, name, db[name.removesuffix("_col")])

    db["states"].insert_many([{"code": "WB", "name": "West Bengal"}, {"code": "BR", "name": "Bihar"}])
    db["districts"].insert_many([
        {"code": "319", "state_code": "WB", "name": "Murshidabad"},
        {"code": "320", "state_code": "WB", "name": "Nadia"},
        {"code": "101", "state_code": "BR", "name": "Patna"},
    ])

    def user(role, name, email, jurisdiction=None, **extra):
        doc = {"name": name, "email": email, "role": role, "status": "active", "token_version": 0, **extra}
        if jurisdiction:
            doc["jurisdiction"] = jurisdiction
        doc["_id"] = db["users"].insert_one(doc).inserted_id
        doc["headers"] = {"Authorization": f"Bearer {create_access_token(str(doc['_id']), 0)}"}
        return doc

    w = {
        "db": db,
        "owner": user("owner", "Anil", "a@example.com", org_name="Alpha Traders"),
        "admin": user("admin", "Minister", "admin@example.com"),
        "lmo": user("lmo", "Ravi", "ravi@example.com", {"state_code": "WB", "district_code": "319"}),
        "gatc": user("gatc", "Sita", "sita@example.com", {"state_code": "WB", "district_code": None}),
        "lmo_nowhere": user("lmo", "Nobody", "nobody@example.com"),
    }

    n = [0]

    def instrument(state, district, registered_days_ago=None, owner=None):
        """Instruments carry no date field; the registration time is the one inside the ObjectId."""
        n[0] += 1
        doc = {
            "owner_id": (owner or w["owner"])["_id"], "uiid": f"LM-26-{n[0]:08d}", "type": "Platform Scale",
            "location": {"state_code": state, "district_code": district, "address_line": f"{n[0]} Main Road"},
        }
        if registered_days_ago is not None:
            # ObjectId.from_datetime() zero-fills everything after the 4-byte timestamp, so two instruments
            # with the same age would share an _id (DuplicateKeyError). Keep the timestamp (that is the
            # registration time the app reads) and randomise the remaining 8 bytes.
            stamp = ObjectId.from_datetime(_ist_noon(registered_days_ago)).binary[:4]
            doc["_id"] = ObjectId(stamp + os.urandom(8))
        return db["instruments"].insert_one(doc).inserted_id

    def application(inst, status, state, district, submitted_days_ago, officer=None, **extra):
        return db["applications"].insert_one({
            "owner_id": w["owner"]["_id"], "instrument_id": inst, "status": status, "state_code": state,
            "district_code": district, "submitted_at": _ago(days=submitted_days_ago),
            "assigned_officer_id": officer, "application_type": "initial", "history": [], **extra,
        }).inserted_id

    def certificate(inst, valid_until_days_ago, cert_no):
        return db["certificates"].insert_one({
            "instrument_id": inst, "cert_no": cert_no, "valid_until": _ago(days=valid_until_days_ago),
        }).inserted_id

    w.update(instrument=instrument, application=application, certificate=certificate, user=user)
    return w


def _get(client, w, who, path, **params):
    headers = w[who]["headers"] if who else {}
    return client.get(f"{BASE}/{path}", headers=headers, params=params)


# ------------------------------------------------------------------ access control


@pytest.mark.parametrize("path", ["pendency", "districts", "enforcement", "uncertified", "cases"])
def test_owner_and_anonymous_are_refused(client, world, path):
    assert _get(client, world, "owner", path).status_code == 403
    assert _get(client, world, None, path).status_code in (401, 403)


@pytest.mark.parametrize("path", ["pendency", "districts", "enforcement", "uncertified"])
def test_officer_without_jurisdiction_sees_nothing(client, world, path):
    i = world["instrument"]("WB", "319")
    world["application"](i, "submitted", "WB", "319", 3)
    world["application"](i, "expired", "WB", "319", 400)
    world["certificate"](i, 40, "CERT-1")
    body = _get(client, world, "lmo_nowhere", path).json()
    assert body.get("total_open", body.get("total", 0)) == 0
    assert body.get("rows", []) == [] and body.get("items", []) == []


# ------------------------------------------------------------------ pendency ageing


def test_pendency_buckets_status_and_age(client, world):
    w = world
    w["application"](w["instrument"]("WB", "319"), "submitted", "WB", "319", 2)
    w["application"](w["instrument"]("WB", "319"), "scheduled", "WB", "319", 7, officer=w["lmo"]["_id"])
    w["application"](w["instrument"]("WB", "320"), "inspected", "WB", "320", 8, officer=w["lmo"]["_id"])
    w["application"](w["instrument"]("WB", "320"), "submitted", "WB", "320", 31)
    w["application"](w["instrument"]("BR", "101"), "submitted", "BR", "101", 200)
    # Finished applications never count as pending.
    w["application"](w["instrument"]("WB", "319"), "certified", "WB", "319", 90)
    w["application"](w["instrument"]("WB", "319"), "rejected", "WB", "319", 90)

    r = _get(client, w, "admin", "pendency")
    assert r.status_code == 200
    body = r.json()
    counts = {b["label"]: b["count"] for b in body["buckets"]}
    assert counts == {"0-7 days": 2, "8-14 days": 1, "15-30 days": 0, "31-60 days": 1, "Over 60 days": 1}
    assert body["total_open"] == 5
    assert body["by_status"] == {"submitted": 3, "scheduled": 1, "inspected": 1}
    assert body["unassigned"] == 3
    assert body["target_days"] == 30
    assert body["over_target"] == 2  # 31 and 200 days
    ages = [o["age_days"] for o in body["oldest"]]
    assert ages == sorted(ages, reverse=True) and ages[0] == 200
    assert body["oldest"][0]["district_name"] == "Patna" and body["oldest"][0]["uiid"].startswith("LM-26-")


def test_pendency_bucket_edges(client, world):
    w = world
    for days in (7, 8, 14, 15, 30, 31, 60, 61):
        w["db"]["applications"].insert_one({
            "owner_id": w["owner"]["_id"], "instrument_id": w["instrument"]("WB", "319"), "status": "submitted",
            "state_code": "WB", "district_code": "319", "submitted_at": _ist_noon(days),
            "assigned_officer_id": None, "history": [],
        })
    counts = [b["count"] for b in _get(client, w, "admin", "pendency").json()["buckets"]]
    # Ages are India calendar days, so each one lands in its bucket whatever the time of day.
    assert counts == [1, 2, 2, 2, 1]


def test_ages_follow_the_india_calendar_not_24_hour_blocks(client, world):
    w = world
    midnight = _ist_midnight()
    # 10 minutes after India midnight is today (age 0); 10 minutes before it is yesterday (age 1),
    # even though the two are only 20 minutes apart.
    for when in (midnight + timedelta(minutes=10), midnight - timedelta(minutes=10)):
        w["db"]["applications"].insert_one({
            "owner_id": w["owner"]["_id"], "instrument_id": w["instrument"]("WB", "319"), "status": "submitted",
            "state_code": "WB", "district_code": "319", "submitted_at": when, "assigned_officer_id": None, "history": [],
        })
    ages = sorted(i["age_days"] for i in _get(client, w, "admin", "pendency").json()["oldest"])
    assert ages == [0, 1]
    csv_ages = sorted(int(x["Days waiting"]) for x in _csv_rows(client.get(f"{REPORTS}/oversight-pendency", headers=w["admin"]["headers"])))
    assert csv_ages == [0, 1]


def test_over_target_counts_calendar_days_in_india(client, world):
    w = world
    # Target is 30 days: 30 calendar days is on target, 31 is over (noon, so the time of day never matters).
    for days in (30, 31):
        w["db"]["applications"].insert_one({
            "owner_id": w["owner"]["_id"], "instrument_id": w["instrument"]("WB", "319"), "status": "submitted",
            "state_code": "WB", "district_code": "319", "submitted_at": _ist_noon(days), "assigned_officer_id": None, "history": [],
        })
    assert _get(client, w, "admin", "pendency").json()["over_target"] == 1
    assert _get(client, w, "admin", "districts").json()["totals"]["overdue_applications"] == 1


def test_days_overdue_follow_the_india_calendar(client, world):
    w = world
    i = w["instrument"]("WB", "319")
    # Ran out at 23:50 India time yesterday: only minutes ago, but already 1 calendar day overdue.
    w["db"]["certificates"].insert_one({"instrument_id": i, "cert_no": "CERT-LATE", "valid_until": _ist_midnight() - timedelta(minutes=10)})
    body = _get(client, w, "admin", "enforcement").json()
    assert body["items"][0]["days_overdue"] == 1


def test_pendency_is_limited_to_the_officers_jurisdiction(client, world):
    w = world
    w["application"](w["instrument"]("WB", "319"), "submitted", "WB", "319", 3)
    w["application"](w["instrument"]("WB", "320"), "submitted", "WB", "320", 3)
    w["application"](w["instrument"]("BR", "101"), "submitted", "BR", "101", 3)
    assert _get(client, w, "admin", "pendency").json()["total_open"] == 3
    assert _get(client, w, "lmo", "pendency").json()["total_open"] == 1  # own district only
    assert _get(client, w, "gatc", "pendency").json()["total_open"] == 2  # whole state
    # A filter can only narrow: asking an LMO for another district yields nothing, not that district.
    assert _get(client, w, "lmo", "pendency", district_code="320").json()["total_open"] == 0
    assert _get(client, w, "lmo", "pendency", state_code="BR").json()["total_open"] == 0
    assert _get(client, w, "admin", "pendency", state_code="BR").json()["total_open"] == 1


# ------------------------------------------------------------------ district-wise


def test_districts_counts_and_sorting(client, world):
    w = world
    a, b, c = w["instrument"]("WB", "319"), w["instrument"]("WB", "319"), w["instrument"]("WB", "320")
    w["instrument"]("BR", "101")  # registered, no applications yet
    w["application"](a, "submitted", "WB", "319", 45)  # overdue
    w["application"](b, "scheduled", "WB", "319", 5)
    w["application"](a, "certified", "WB", "319", 100)
    w["application"](b, "expiring", "WB", "319", 100)
    w["application"](c, "expired", "WB", "320", 400)

    body = _get(client, w, "admin", "districts").json()
    rows = {(r["state_code"], r["district_code"]): r for r in body["rows"]}
    m = rows[("WB", "319")]
    assert (m["instruments"], m["open_applications"], m["overdue_applications"], m["verified"], m["expired"]) == (2, 2, 1, 2, 0)
    assert m["district_name"] == "Murshidabad" and m["state_name"] == "West Bengal"
    n = rows[("WB", "320")]
    assert (n["instruments"], n["open_applications"], n["expired"]) == (1, 0, 1)
    p = rows[("BR", "101")]
    assert (p["instruments"], p["open_applications"]) == (1, 0)
    assert body["rows"][0]["district_code"] == "319"  # most overdue first
    assert body["totals"] == {"instruments": 4, "open_applications": 2, "overdue_applications": 1, "verified": 2, "expired": 1}


def test_districts_scoping_and_filter(client, world):
    w = world
    for state, district in [("WB", "319"), ("WB", "320"), ("BR", "101")]:
        w["application"](w["instrument"](state, district), "submitted", state, district, 3)
    assert {r["district_code"] for r in _get(client, w, "lmo", "districts").json()["rows"]} == {"319"}
    assert {r["district_code"] for r in _get(client, w, "gatc", "districts").json()["rows"]} == {"319", "320"}
    assert {r["district_code"] for r in _get(client, w, "admin", "districts", state_code="BR").json()["rows"]} == {"101"}
    assert _get(client, w, "lmo", "districts", district_code="320").json()["rows"] == []


# ------------------------------------------------------------------ enforcement


def _lapsed(w, state, district, valid_until_days_ago, cert_no, applied=None):
    i = w["instrument"](state, district)
    w["application"](i, "expired", state, district, valid_until_days_ago + 365)
    w["certificate"](i, valid_until_days_ago, cert_no)
    if applied:
        w["application"](i, applied, state, district, 2)
    return i


def test_enforcement_lists_lapsed_instruments_most_overdue_first(client, world):
    w = world
    _lapsed(w, "WB", "319", 10, "CERT-A")
    _lapsed(w, "WB", "319", 120, "CERT-B")
    _lapsed(w, "WB", "320", 45, "CERT-C", applied="scheduled")
    body = _get(client, w, "admin", "enforcement").json()
    assert [i["cert_no"] for i in body["items"]] == ["CERT-B", "CERT-C", "CERT-A"]
    assert body["total"] == 3 and not body["truncated"]
    assert body["summary"] == {
        "lapsed": 3, "reverification_applied": 1, "no_reverification": 2, "recent": 1, "overdue": 1, "long_overdue": 1,
    }
    top = body["items"][0]
    assert (top["days_overdue"], top["band"]) == (120, "long_overdue")
    assert top["org_name"] == "Alpha Traders" and top["owner_name"] == "Anil"
    assert top["district_name"] == "Murshidabad" and top["address_line"].endswith("Main Road")
    assert top["reverification"] is None
    mitigated = body["items"][1]
    assert mitigated["reverification"]["status"] == "scheduled" and mitigated["band"] == "overdue"
    assert "owner_id" not in top and "contact" not in top


def test_enforcement_skips_instruments_that_were_renewed_or_are_still_valid(client, world):
    w = world
    renewed = _lapsed(w, "WB", "319", 60, "CERT-OLD")
    w["application"](renewed, "certified", "WB", "319", 20)
    w["certificate"](renewed, -300, "CERT-NEW")  # newer certificate, still in force
    still_valid = w["instrument"]("WB", "319")
    w["application"](still_valid, "expired", "WB", "319", 500)  # stale status, but a valid certificate exists
    w["certificate"](still_valid, -10, "CERT-OK")
    _lapsed(w, "WB", "319", 5, "CERT-LAPSED")
    never_certified = w["instrument"]("WB", "319")
    w["application"](never_certified, "submitted", "WB", "319", 90)
    body = _get(client, w, "admin", "enforcement").json()
    assert [i["cert_no"] for i in body["items"]] == ["CERT-LAPSED"]


def test_enforcement_uses_the_newest_certificate_of_an_instrument(client, world):
    w = world
    i = _lapsed(w, "WB", "319", 100, "CERT-1")
    w["application"](i, "expired", "WB", "319", 200)
    w["certificate"](i, 30, "CERT-2")  # renewed once, and that one has lapsed too
    body = _get(client, w, "admin", "enforcement").json()
    assert body["total"] == 1 and body["items"][0]["cert_no"] == "CERT-2" and body["items"][0]["days_overdue"] == 30


def test_enforcement_filters_and_paging(client, world):
    w = world
    for k, days in enumerate((10, 50, 100, 200)):
        _lapsed(w, "WB", "319", days, f"CERT-{k}", applied="submitted" if k % 2 else None)
    _lapsed(w, "BR", "101", 70, "CERT-BR")
    get = lambda **p: _get(client, w, "admin", "enforcement", **p).json()  # noqa: E731
    assert get(reverification="applied")["total"] == 2
    assert get(reverification="none")["total"] == 3
    assert get(min_days_overdue=60)["total"] == 3
    assert get(state_code="BR")["items"][0]["cert_no"] == "CERT-BR"
    page1, page2 = get(page_size=2), get(page_size=2, page=2)
    assert [len(page1["items"]), len(page2["items"]), page1["total"]] == [2, 2, 5]
    assert page1["items"][0]["days_overdue"] >= page2["items"][0]["days_overdue"]
    # The summary covers every match, not just the page.
    assert page1["summary"]["lapsed"] == 5
    assert _get(client, w, "admin", "enforcement", page_size=101).status_code == 422
    assert _get(client, w, "admin", "enforcement", reverification="maybe").status_code == 422


def test_enforcement_is_limited_to_the_officers_jurisdiction(client, world):
    w = world
    _lapsed(w, "WB", "319", 10, "CERT-MINE")
    _lapsed(w, "WB", "320", 10, "CERT-NEIGHBOUR")
    _lapsed(w, "BR", "101", 10, "CERT-OTHER-STATE")
    assert [i["cert_no"] for i in _get(client, w, "lmo", "enforcement").json()["items"]] == ["CERT-MINE"]
    assert {i["cert_no"] for i in _get(client, w, "gatc", "enforcement").json()["items"]} == {"CERT-MINE", "CERT-NEIGHBOUR"}
    assert _get(client, w, "admin", "enforcement").json()["total"] == 3
    assert _get(client, w, "lmo", "enforcement", state_code="BR").json()["total"] == 0


def test_enforcement_does_not_wait_for_the_expiry_job(client, world):
    """A lapsed certificate counts even if its application was never moved to `expired`, or has none."""
    w = world
    stale = w["instrument"]("WB", "319")
    w["application"](stale, "certified", "WB", "319", 400)  # the hourly job has not caught up yet
    w["certificate"](stale, 12, "CERT-STALE")
    orphan = w["instrument"]("WB", "320")  # certificate on file, no application document at all
    w["certificate"](orphan, 3, "CERT-ORPHAN")
    body = _get(client, w, "admin", "enforcement").json()
    assert [i["cert_no"] for i in body["items"]] == ["CERT-STALE", "CERT-ORPHAN"]
    assert body["truncated"] is False


def test_enforcement_place_comes_from_the_instrument_and_scopes_officers(client, world):
    w = world
    mine = w["instrument"]("WB", "319")
    w["certificate"](mine, 10, "CERT-MINE")
    elsewhere = w["instrument"]("WB", "320")
    w["certificate"](elsewhere, 10, "CERT-NEIGHBOUR")
    # No application rows exist, so the old application-based scoping would have shown nothing here.
    assert [i["cert_no"] for i in _get(client, w, "lmo", "enforcement").json()["items"]] == ["CERT-MINE"]
    assert _get(client, w, "gatc", "enforcement").json()["total"] == 2
    assert _get(client, w, "admin", "enforcement", district_code="320").json()["items"][0]["cert_no"] == "CERT-NEIGHBOUR"


def test_enforcement_lists_every_lapsed_instrument_without_a_scan_cut(client, world):
    for k in range(25):
        _lapsed(world, "WB", "319", 10 + k, f"CERT-{k}")
    body = _get(client, world, "admin", "enforcement", page_size=100).json()
    assert body["total"] == 25 and body["truncated"] is False and len(body["items"]) == 25


def test_enforcement_safety_ceiling_keeps_the_most_overdue(client, world, monkeypatch):
    import app.routers.oversight as mod

    monkeypatch.setattr(mod, "ENFORCEMENT_MAX_SCAN", 2)
    for k in range(3):
        _lapsed(world, "WB", "319", 10 + k * 10, f"CERT-{k}")  # 10, 20, 30 days overdue
    body = _get(client, world, "admin", "enforcement").json()
    assert body["truncated"] is True and body["total"] == 2
    assert [i["cert_no"] for i in body["items"]] == ["CERT-2", "CERT-1"]


# ------------------------------------------------------------------ CSV / PDF exports

REPORTS = "/api/v1/reports"


def _csv_rows(resp):
    import csv
    import io

    return list(csv.DictReader(io.StringIO(resp.content.decode("utf-8-sig"))))


@pytest.mark.parametrize("kind", ["oversight-pendency", "oversight-districts", "oversight-enforcement", "oversight-uncertified"])
def test_oversight_exports_are_refused_to_owners_and_anonymous(client, world, kind):
    assert client.get(f"{REPORTS}/{kind}", headers=world["owner"]["headers"]).status_code == 403
    assert client.get(f"{REPORTS}/{kind}").status_code in (401, 403)


def test_enforcement_csv_matches_the_screen_and_follows_filters(client, world):
    w = world
    _lapsed(w, "WB", "319", 120, "CERT-B")
    _lapsed(w, "WB", "319", 10, "CERT-A", applied="scheduled")
    _lapsed(w, "BR", "101", 40, "CERT-BR")
    r = client.get(f"{REPORTS}/oversight-enforcement", headers=w["admin"]["headers"])
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.headers["x-report-rows"] == "3" and r.headers["x-report-truncated"] == "false"
    rows = _csv_rows(r)
    assert [x["Certificate no."] for x in rows] == ["CERT-B", "CERT-BR", "CERT-A"]
    assert rows[0]["Band"] == "Over 90 days" and rows[0]["Re-verification"] == "Not applied"
    assert rows[2]["Re-verification"] == "Applied - Scheduled"
    assert "contact" not in r.text.lower() and "email" not in r.text.lower()
    only = client.get(f"{REPORTS}/oversight-enforcement", headers=w["admin"]["headers"], params={"min_days_overdue": 60})
    assert [x["Certificate no."] for x in _csv_rows(only)] == ["CERT-B"]


def test_oversight_exports_never_widen_an_officers_scope(client, world):
    w = world
    _lapsed(w, "WB", "319", 10, "CERT-MINE")
    _lapsed(w, "WB", "320", 10, "CERT-NEIGHBOUR")
    w["application"](w["instrument"]("WB", "319"), "submitted", "WB", "319", 5)
    w["application"](w["instrument"]("BR", "101"), "submitted", "BR", "101", 5)
    enforcement = client.get(f"{REPORTS}/oversight-enforcement", headers=w["lmo"]["headers"])
    assert [x["Certificate no."] for x in _csv_rows(enforcement)] == ["CERT-MINE"]
    pendency = client.get(f"{REPORTS}/oversight-pendency", headers=w["lmo"]["headers"])
    assert len(_csv_rows(pendency)) == 1
    nowhere = client.get(f"{REPORTS}/oversight-pendency", headers=w["lmo_nowhere"]["headers"])
    assert nowhere.status_code == 200 and _csv_rows(nowhere) == []
    # A filter can only narrow: asking for another state gives an empty file, not that state's rows.
    other = client.get(f"{REPORTS}/oversight-enforcement", headers=w["lmo"]["headers"], params={"state_code": "BR"})
    assert _csv_rows(other) == []


def test_pendency_and_district_exports(client, world):
    w = world
    w["application"](w["instrument"]("WB", "319"), "submitted", "WB", "319", 45)
    w["application"](w["instrument"]("WB", "320"), "scheduled", "WB", "320", 3, officer=w["lmo"]["_id"])
    w["application"](w["instrument"]("WB", "320"), "certified", "WB", "320", 100)  # finished: not pending
    pend = _csv_rows(client.get(f"{REPORTS}/oversight-pendency", headers=w["admin"]["headers"]))
    assert [(x["Days waiting"], x["Over 30 days"], x["Officer"]) for x in pend] == [("45", "Yes", "Unassigned"), ("3", "No", "Assigned")]
    dist = _csv_rows(client.get(f"{REPORTS}/oversight-districts", headers=w["admin"]["headers"]))
    by_name = {x["District"]: x for x in dist}
    assert by_name["Murshidabad"]["Open applications"] == "1" and by_name["Nadia"]["Verified"] == "1"


@pytest.mark.parametrize("kind", ["oversight-pendency", "oversight-districts", "oversight-enforcement", "oversight-uncertified"])
def test_oversight_pdf_exports_and_audit(client, world, kind):
    _lapsed(world, "WB", "319", 10, "CERT-A")
    world["application"](world["instrument"]("WB", "319"), "submitted", "WB", "319", 5)
    r = client.get(f"{REPORTS}/{kind}", headers=world["admin"]["headers"], params={"format": "pdf"})
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert world["db"]["audit_logs"].count_documents({"event": "report_exported"}) == 1


def test_oversight_export_limit_keeps_the_most_overdue_and_says_so(client, world, monkeypatch):
    import app.routers.reports as reports_mod

    monkeypatch.setattr(reports_mod, "REPORT_MAX_ROWS", 2)
    for k in range(3):
        _lapsed(world, "WB", "319", 10 + k * 10, f"CERT-{k}")
    r = client.get(f"{REPORTS}/oversight-enforcement", headers=world["admin"]["headers"])
    assert (r.headers["x-report-rows"], r.headers["x-report-total"], r.headers["x-report-truncated"]) == ("2", "3", "true")
    assert [x["Certificate no."] for x in _csv_rows(r)] == ["CERT-2", "CERT-1"]


# ------------------------------------------------------------------ never certified


def test_uncertified_lists_only_old_instruments_with_no_certificate(client, world):
    w = world
    w["instrument"]("WB", "319", registered_days_ago=45)          # listed: 45 days, no certificate
    w["instrument"]("WB", "319", registered_days_ago=30)          # exactly on the grace limit: not yet
    w["instrument"]("WB", "319", registered_days_ago=31)          # listed: one day past it
    w["instrument"]("WB", "319", registered_days_ago=5)           # too recent
    valid = w["instrument"]("WB", "319", registered_days_ago=90)  # has a valid certificate
    w["certificate"](valid, -200, "CERT-VALID")
    lapsed = w["instrument"]("WB", "319", registered_days_ago=90)  # lapsed: belongs to the other list
    w["certificate"](lapsed, 10, "CERT-OLD")
    body = _get(client, w, "admin", "uncertified").json()
    assert body["grace_days"] == 30 and body["truncated"] is False
    assert [i["days_since_registered"] for i in body["items"]] == [45, 31]  # longest registered first
    assert body["summary"] == {"total": 2, "applied": 0, "not_applied": 2}
    assert {i["instrument_type"] for i in body["items"]} == {"Platform Scale"}
    assert _get(client, w, "admin", "enforcement").json()["total"] == 1  # the lapsed one only


def test_uncertified_marks_an_open_application_and_filters_on_it(client, world):
    w = world
    applied = w["instrument"]("WB", "319", registered_days_ago=60)
    w["application"](applied, "scheduled", "WB", "319", 12)
    w["application"](applied, "rejected", "WB", "319", 50)  # an old failed attempt is not a pending application
    w["instrument"]("WB", "319", registered_days_ago=40)
    body = _get(client, w, "admin", "uncertified").json()
    by_days = {i["days_since_registered"]: i for i in body["items"]}
    assert by_days[60]["application"]["status"] == "scheduled" and by_days[40]["application"] is None
    assert body["summary"] == {"total": 2, "applied": 1, "not_applied": 1}
    only_none = _get(client, w, "admin", "uncertified", application="none").json()
    assert [i["days_since_registered"] for i in only_none["items"]] == [40]
    assert _get(client, w, "admin", "uncertified", min_days=50).json()["total"] == 1


def test_uncertified_follows_jurisdiction_and_place_filters(client, world):
    w = world
    w["instrument"]("WB", "319", registered_days_ago=40)
    w["instrument"]("WB", "320", registered_days_ago=40)
    w["instrument"]("BR", "101", registered_days_ago=40)
    assert _get(client, w, "lmo", "uncertified").json()["total"] == 1
    assert _get(client, w, "gatc", "uncertified").json()["total"] == 2
    assert _get(client, w, "admin", "uncertified").json()["total"] == 3
    one = _get(client, w, "admin", "uncertified", state_code="BR").json()["items"][0]
    assert (one["state_name"], one["district_name"]) == ("Bihar", "Patna")
    assert _get(client, w, "lmo", "uncertified", state_code="BR").json()["total"] == 0


def test_uncertified_csv_export(client, world):
    w = world
    w["instrument"]("WB", "319", registered_days_ago=45)
    r = client.get(f"{REPORTS}/oversight-uncertified", headers=w["admin"]["headers"])
    rows = _csv_rows(r)
    assert r.status_code == 200 and len(rows) == 1
    assert rows[0]["Days since registered"] == "45" and rows[0]["Application"] == "Not applied" and rows[0]["Case"] == ""
    assert "email" not in r.text.lower() and "phone" not in r.text.lower()


# ------------------------------------------------------------------ enforcement cases

CASES = f"{BASE}/cases"


def _post(client, w, who, path, **body):
    return client.post(f"{CASES}{path}", headers=w[who]["headers"], json=body)


def _open(client, w, who, instrument_id):
    r = _post(client, w, who, "", instrument_id=str(instrument_id))
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def mail(monkeypatch):
    """Pretend mail is configured and record what would be sent."""
    import app.services.owner_notifications as notif

    sent = []
    monkeypatch.setattr(notif, "can_email_owner", lambda owner_id: True)
    monkeypatch.setattr(notif, "notify_enforcement_notice", lambda case, instrument, **kw: sent.append((case, instrument, kw)))
    return sent


def _lapsed_instrument(w, district="319", days=40, cert="CERT-L"):
    i = w["instrument"]("WB", district)
    w["certificate"](i, days, cert)
    return i


def test_open_case_for_a_lapsed_instrument_is_idempotent(client, world):
    w = world
    i = _lapsed_instrument(w)
    case = _open(client, w, "lmo", i)
    assert (case["kind"], case["status"], case["level"]) == ("lapsed", "open", "lmo")
    assert case["cert_no"] == "CERT-L" and case["notice_count"] == 0
    assert [e["action"] for e in case["events"]] == ["opened"] and case["events"][0]["by_name"] == "Ravi"
    assert case["can"] == {"note": True, "notice": True, "escalate": True, "close": True, "notice_available_on": None}
    assert _open(client, w, "lmo", i)["id"] == case["id"]
    assert w["db"]["enforcement_cases"].count_documents({}) == 1
    assert w["db"]["audit_logs"].count_documents({"event": "enforcement_case_opened"}) == 1


def test_open_case_for_a_never_certified_instrument(client, world):
    w = world
    old = w["instrument"]("WB", "319", registered_days_ago=45)
    case = _open(client, w, "lmo", old)
    assert case["kind"] == "never_certified" and case["registered_on"] and case["cert_no"] is None
    recent = w["instrument"]("WB", "319", registered_days_ago=10)
    assert _post(client, w, "lmo", "", instrument_id=str(recent)).status_code == 409


def test_open_case_is_refused_when_it_does_not_apply_or_is_out_of_reach(client, world):
    w = world
    valid = w["instrument"]("WB", "319")
    w["certificate"](valid, -100, "CERT-OK")
    assert _post(client, w, "lmo", "", instrument_id=str(valid)).status_code == 409
    elsewhere = _lapsed_instrument(w, district="320")
    assert _post(client, w, "lmo", "", instrument_id=str(elsewhere)).status_code == 404  # outside the LMO's district
    assert _post(client, w, "gatc", "", instrument_id=str(elsewhere)).status_code == 200  # inside the GATC's state
    assert _post(client, w, "lmo", "", instrument_id="not-an-id").status_code == 404
    assert _post(client, w, "owner", "", instrument_id=str(elsewhere)).status_code == 403


def test_notice_is_recorded_emailed_and_rate_limited(client, world, mail):
    w = world
    i = _lapsed_instrument(w)
    case = _open(client, w, "lmo", i)
    r = _post(client, w, "lmo", f"/{case['id']}/notice", message="  Please renew this week.  ")
    assert r.status_code == 200
    body = r.json()
    assert (body["status"], body["notice_count"]) == ("notice_sent", 1)
    notice = body["events"][-1]
    assert (notice["action"], notice["text"], notice["emailed"]) == ("notice", "Please renew this week.", True)
    assert len(mail) == 1 and mail[0][2]["dedupe_key"] == f"enforcement_notice:{case['id']}:1"
    assert mail[0][2]["issued_by"] == "Legal Metrology Officer" and mail[0][2]["cert"]["cert_no"] == "CERT-L"
    assert body["can"]["notice"] is False and body["can"]["notice_available_on"]
    assert _post(client, w, "lmo", f"/{case['id']}/notice").status_code == 409  # too soon after the last one
    # Once the gap has passed a follow-up goes out as notice number 2.
    w["db"]["enforcement_cases"].update_one({}, {"$set": {"last_notice_at": _ago(days=5)}})
    again = _post(client, w, "lmo", f"/{case['id']}/notice")
    assert again.status_code == 200 and again.json()["notice_count"] == 2
    assert mail[1][2]["dedupe_key"] == f"enforcement_notice:{case['id']}:2"
    assert w["db"]["audit_logs"].count_documents({"event": "enforcement_notice_sent"}) == 2


def test_notice_is_still_recorded_when_no_email_can_be_sent(client, world):
    w = world  # no mail configured in tests
    case = _open(client, w, "lmo", _lapsed_instrument(w))
    body = _post(client, w, "lmo", f"/{case['id']}/notice").json()
    assert body["notice_count"] == 1 and body["events"][-1]["emailed"] is False


def test_only_the_level_holding_a_case_may_act_but_anyone_in_scope_may_note(client, world, mail):
    w = world
    case = _open(client, w, "lmo", _lapsed_instrument(w))
    cid = case["id"]
    assert _post(client, w, "gatc", f"/{cid}/notice").status_code == 403  # the case is with the LMO
    assert _post(client, w, "gatc", f"/{cid}/escalate").status_code == 403
    assert _post(client, w, "gatc", f"/{cid}/close", reason="x").status_code == 403
    noted = _post(client, w, "gatc", f"/{cid}/note", text="Owner called, says cheque sent.")
    assert noted.status_code == 200 and noted.json()["events"][-1]["by_role"] == "gatc"
    assert _post(client, w, "lmo", f"/{cid}/note", text="   ").status_code == 400
    assert _post(client, w, "admin", f"/{cid}/notice").status_code == 200  # an admin may always act
    assert client.get(f"{CASES}/{cid}", headers=w["lmo_nowhere"]["headers"]).status_code == 404


def test_escalation_moves_a_case_up_the_chain(client, world, mail):
    w = world
    cid = _open(client, w, "lmo", _lapsed_instrument(w))["id"]
    up = _post(client, w, "lmo", f"/{cid}/escalate", reason="Owner ignores calls")
    assert up.status_code == 200
    body = up.json()
    assert (body["level"], body["status"]) == ("gatc", "escalated")
    assert body["events"][-1]["to_level"] == "gatc" and body["events"][-1]["text"] == "Owner ignores calls"
    assert body["can"]["notice"] is False and body["can"]["note"] is True and body["held_by_me"] is False
    assert _post(client, w, "lmo", f"/{cid}/notice").status_code == 403  # no longer the LMO's
    assert _post(client, w, "gatc", f"/{cid}/notice").status_code == 200
    again = _post(client, w, "gatc", f"/{cid}/escalate")
    assert again.json()["level"] == "admin"
    assert _post(client, w, "admin", f"/{cid}/escalate").status_code == 409  # nowhere higher
    assert w["db"]["audit_logs"].count_documents({"event": "enforcement_case_escalated"}) == 2


def test_closing_a_case_keeps_the_history_and_allows_a_new_one(client, world):
    w = world
    i = _lapsed_instrument(w)
    cid = _open(client, w, "lmo", i)["id"]
    assert _post(client, w, "lmo", f"/{cid}/close", reason="").status_code == 422
    closed = _post(client, w, "lmo", f"/{cid}/close", reason="Instrument scrapped, owner confirmed")
    assert closed.status_code == 200
    assert (closed.json()["status"], closed.json()["resolution"]) == ("resolved", "closed")
    assert _post(client, w, "lmo", f"/{cid}/notice").status_code == 409  # a resolved case takes no action
    second = _open(client, w, "lmo", i)
    assert second["id"] != cid and w["db"]["enforcement_cases"].count_documents({}) == 2
    assert w["db"]["audit_logs"].count_documents({"event": "enforcement_case_closed"}) == 1


def test_case_resolves_itself_when_the_instrument_gets_a_certificate(client, world):
    w = world
    lapsed = _lapsed_instrument(w)
    never = w["instrument"]("WB", "319", registered_days_ago=45)
    a, b = _open(client, w, "lmo", lapsed)["id"], _open(client, w, "lmo", never)["id"]
    w["certificate"](lapsed, -365, "CERT-RENEWED")
    w["certificate"](never, -365, "CERT-FIRST")
    renewed = client.get(f"{CASES}/{a}", headers=w["lmo"]["headers"]).json()
    assert (renewed["status"], renewed["resolution"]) == ("resolved", "renewed")
    assert renewed["events"][-1]["by_name"] is None  # done by the system
    certified = client.get(f"{CASES}/{b}", headers=w["lmo"]["headers"]).json()
    assert certified["resolution"] == "certified"


def test_lists_show_the_open_case_next_to_the_instrument(client, world):
    w = world
    i = _lapsed_instrument(w)
    n = w["instrument"]("WB", "319", registered_days_ago=45)
    cid = _open(client, w, "lmo", i)["id"]
    _open(client, w, "lmo", n)
    lapsed_row = _get(client, w, "admin", "enforcement").json()["items"][0]
    assert lapsed_row["case"] == {"id": cid, "status": "open", "level": "lmo"}
    assert _get(client, w, "admin", "uncertified").json()["items"][0]["case"]["status"] == "open"
    assert "Open - Legal Metrology Officer" in client.get(f"{REPORTS}/oversight-enforcement", headers=w["admin"]["headers"]).text


def test_case_list_summary_filters_and_scope(client, world, mail):
    w = world
    a = _open(client, w, "lmo", _lapsed_instrument(w, cert="C-A"))["id"]
    b = _open(client, w, "lmo", w["instrument"]("WB", "319", registered_days_ago=45))["id"]
    c = _open(client, w, "gatc", _lapsed_instrument(w, district="320", cert="C-C"))["id"]
    _post(client, w, "lmo", f"/{a}/notice")
    w["db"]["enforcement_cases"].update_one({"kind": "lapsed", "level": "lmo"}, {"$set": {"last_notice_at": _ago(days=20)}})
    _post(client, w, "lmo", f"/{b}/escalate")

    body = client.get(CASES, headers=w["gatc"]["headers"]).json()
    assert body["total"] == 3
    assert body["summary"] == {"active": 3, "open": 1, "notice_sent": 1, "escalated": 1, "escalation_due": 1, "with_me": 2, "resolved": 0}
    mine = client.get(CASES, headers=w["lmo"]["headers"]).json()
    assert mine["total"] == 2 and {i["id"] for i in mine["items"]} == {a, b}  # not the district-320 case
    assert {i["id"] for i in client.get(CASES, headers=w["gatc"]["headers"], params={"due": "true"}).json()["items"]} == {a}
    assert {i["id"] for i in client.get(CASES, headers=w["gatc"]["headers"], params={"kind": "never_certified"}).json()["items"]} == {b}
    assert {i["id"] for i in client.get(CASES, headers=w["gatc"]["headers"], params={"with_me": "true"}).json()["items"]} == {b, c}
    one = client.get(CASES, headers=w["gatc"]["headers"], params={"status": "notice_sent"}).json()["items"][0]
    assert one["escalation_due"] is True and one["instrument"]["uiid"] and one["owner"]["org_name"] == "Alpha Traders"
    assert "email" not in str(body).lower() and "phone" not in str(body).lower()
    page = client.get(CASES, headers=w["admin"]["headers"], params={"page_size": 2, "page": 2}).json()
    assert page["total"] == 3 and len(page["items"]) == 1


def test_hourly_job_resolves_and_escalates(client, world):
    from app.services import enforcement_cases as svc

    w = world
    stale = _open(client, w, "lmo", _lapsed_instrument(w, cert="C-1"))["id"]
    fresh = _open(client, w, "lmo", _lapsed_instrument(w, cert="C-2"))["id"]
    top = _open(client, w, "admin", _lapsed_instrument(w, cert="C-3"))["id"]
    done = _lapsed_instrument(w, cert="C-4")
    renewed = _open(client, w, "lmo", done)["id"]
    cases = w["db"]["enforcement_cases"]
    for cid, days in ((stale, 20), (fresh, 5), (top, 40)):
        cases.update_one({"_id": ObjectId(cid)}, {"$set": {"status": "notice_sent", "last_notice_at": _ago(days=days), "notice_count": 1}})
    w["certificate"](done, -100, "C-4-NEW")

    assert svc.run_maintenance() == {"resolved": 1, "escalated": 1}
    level = lambda cid: cases.find_one({"_id": ObjectId(cid)})["level"]  # noqa: E731
    assert (level(stale), level(fresh), level(top)) == ("gatc", "lmo", "admin")
    moved = cases.find_one({"_id": ObjectId(stale)})
    assert moved["status"] == "escalated" and moved["events"][-1]["by_name"] is None
    assert cases.find_one({"_id": ObjectId(renewed)})["active"] is False
    assert svc.run_maintenance() == {"resolved": 0, "escalated": 0}  # nothing left to do
    assert w["db"]["audit_logs"].count_documents({"event": "enforcement_case_escalated"}) == 1


def test_owner_sees_open_notices_but_nothing_internal(client, world, mail):
    w = world
    mine = _lapsed_instrument(w, cert="C-MINE")
    other_owner = w["user"]("owner", "Bina", "b@example.com", org_name="Beta Stores")
    theirs = w["instrument"]("WB", "319", owner=other_owner)
    w["certificate"](theirs, 40, "C-THEIRS")
    mine_case = _open(client, w, "lmo", mine)["id"]
    theirs_case = _open(client, w, "lmo", theirs)["id"]
    notices = lambda who: client.get("/api/v1/notices/mine", headers=w[who]["headers"])  # noqa: E731
    assert notices("owner").json() == []  # a case with no notice yet is not shown
    _post(client, w, "lmo", f"/{mine_case}/note", text="internal: owner is difficult")
    _post(client, w, "lmo", f"/{mine_case}/notice", message="Renew this week")
    _post(client, w, "lmo", f"/{theirs_case}/notice")
    got = notices("owner")
    assert got.status_code == 200 and len(got.json()) == 1
    item = got.json()[0]
    assert (item["case_id"], item["kind"], item["message"], item["issued_by"]) == (mine_case, "lapsed", "Renew this week", "Legal Metrology Officer")
    assert "Ravi" not in got.text and "internal" not in got.text
    assert client.get("/api/v1/notices/mine", headers=w["lmo"]["headers"]).status_code == 403
    w["certificate"](mine, -100, "C-MINE-NEW")  # renewed: the notice disappears
    assert notices("owner").json() == []