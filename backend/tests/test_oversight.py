"""#8 Oversight views: pendency ageing, district-wise position and the enforcement list.

Covers the numbers (ageing buckets, per-district counts, lapsed certificates, mitigating re-verification),
the filters, and above all who may see what: owners are refused, officers only see their jurisdiction.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.security import create_access_token

BASE = "/api/v1/oversight"


def _ago(days=0, hours=0) -> datetime:
    """Naive UTC, which is what MongoDB hands back."""
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days, hours=hours)


@pytest.fixture
def world(client, monkeypatch):
    import app.config.db as dbmod
    import app.routers.oversight as mod

    db = dbmod.db
    for name in ["applications_col", "instruments_col", "certificates_col", "users_col", "states_col", "districts_col"]:
        monkeypatch.setattr(mod, name, db[name.removesuffix("_col")])

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

    def instrument(state, district):
        n[0] += 1
        return db["instruments"].insert_one({
            "owner_id": w["owner"]["_id"], "uiid": f"LM-26-{n[0]:08d}", "type": "Platform Scale",
            "location": {"state_code": state, "district_code": district, "address_line": f"{n[0]} Main Road"},
        }).inserted_id

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

    w.update(instrument=instrument, application=application, certificate=certificate)
    return w


def _get(client, w, who, path, **params):
    headers = w[who]["headers"] if who else {}
    return client.get(f"{BASE}/{path}", headers=headers, params=params)


# ------------------------------------------------------------------ access control


@pytest.mark.parametrize("path", ["pendency", "districts", "enforcement"])
def test_owner_and_anonymous_are_refused(client, world, path):
    assert _get(client, world, "owner", path).status_code == 403
    assert _get(client, world, None, path).status_code in (401, 403)


@pytest.mark.parametrize("path", ["pendency", "districts", "enforcement"])
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
            "state_code": "WB", "district_code": "319", "submitted_at": _ago(days=days, hours=1),
            "assigned_officer_id": None, "history": [],
        })
    counts = [b["count"] for b in _get(client, w, "admin", "pendency").json()["buckets"]]
    # 7d1h is 7 whole days old, so it is still in the first bucket; each age lands by its whole days.
    assert counts == [1, 2, 2, 2, 1]


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


def test_enforcement_reports_when_the_scan_limit_is_hit(client, world, monkeypatch):
    import app.routers.oversight as mod

    monkeypatch.setattr(mod, "ENFORCEMENT_MAX_SCAN", 2)
    for k in range(3):
        _lapsed(world, "WB", "319", 10 + k, f"CERT-{k}")
    body = _get(client, world, "admin", "enforcement").json()
    assert body["truncated"] is True and body["total"] == 2
