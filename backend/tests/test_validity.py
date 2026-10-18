"""#9 Certificate validity per instrument type.

Covers the rule lookup, how a certificate is dated from it (including renewals that chain onto the old
expiry), that a rule never rewrites a certificate that already exists, and the admin-only API for
changing the rules.
"""
from datetime import datetime, timedelta, timezone

import mongomock
import pytest
from bson import ObjectId

from app.services import validity as validity_service
from app.services.cert_generator import compute_validity
from app.utils.security import create_access_token

URL = "/api/v1/admin/validity"
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


# ------------------------------------------------------------------ dating a certificate


def test_default_period_is_one_year():
    start, end = compute_validity(NOW, None)
    assert start == NOW and end == NOW + timedelta(days=365)


def test_a_type_specific_period_is_used():
    start, end = compute_validity(NOW, None, 180)
    assert start == NOW and end == NOW + timedelta(days=180)


def test_renewal_inside_the_window_chains_onto_the_old_expiry_with_the_new_period():
    old_end = NOW + timedelta(days=12)
    start, end = compute_validity(NOW, old_end.replace(tzinfo=None), 730)  # Mongo hands back naive datetimes
    assert start == old_end and end == old_end + timedelta(days=730)


def test_renewal_after_expiry_starts_now_with_the_new_period():
    start, end = compute_validity(NOW, NOW - timedelta(days=3), 90)
    assert start == NOW and end == NOW + timedelta(days=90)


# ------------------------------------------------------------------ rule lookup


def test_lookup_falls_back_to_the_default(client):
    assert validity_service.validity_days_for("Platform Scale") == validity_service.default_days() == 365
    assert validity_service.validity_days_for(None) == 365
    assert validity_service.validity_days_for("Something Unknown") == 365


def test_lookup_uses_the_rule_of_that_type_only(client):
    import app.config.db as dbmod

    dbmod.db["validity_rules"].insert_one({"type": "Water Meter", "days": 730})
    assert validity_service.validity_days_for("Water Meter") == 730
    assert validity_service.validity_days_for("Platform Scale") == 365


@pytest.mark.parametrize("days,text", [(365, "1 year"), (730, "2 years"), (180, "180 days"), (1, "1 day"), (400, "400 days")])
def test_label(days, text):
    assert validity_service.label(days) == text


# ------------------------------------------------------------------ certificates take the rule of their type


@pytest.fixture
def issuing(monkeypatch):
    """issue_certificate() against an in-memory database, with PDF rendering, uploads and mail stubbed out."""
    import app.services.cert_generator as gen

    db = mongomock.MongoClient()["validity_issue"]
    for name in ["inspections", "applications", "instruments", "certificates", "users"]:
        monkeypatch.setattr(gen, f"{name}_col", db[name])
    monkeypatch.setattr(validity_service, "validity_rules_col", db["validity_rules"])
    monkeypatch.setattr(gen, "_make_qr_png", lambda url: b"png")
    monkeypatch.setattr(gen, "_generate_pdf_bytes", lambda *a, **k: b"%PDF-1.4")
    monkeypatch.setattr(gen, "upload_bytes", lambda *a, **k: "https://example.test/x")
    monkeypatch.setattr(gen, "notify_certificate_issued", lambda doc: None)

    owner = db["users"].insert_one({"name": "Anil", "role": "owner"}).inserted_id

    def issue(instrument_type):
        inst = db["instruments"].insert_one({"owner_id": owner, "type": instrument_type, "uiid": "LM-1"}).inserted_id
        app = db["applications"].insert_one({"owner_id": owner, "instrument_id": inst, "status": "inspected"}).inserted_id
        insp = db["inspections"].insert_one({"application_id": app, "seal_number": f"S-{ObjectId()}"}).inserted_id
        return gen.issue_certificate(insp)

    return {"db": db, "issue": issue}


def test_certificate_takes_the_period_of_its_instrument_type(issuing):
    issuing["db"]["validity_rules"].insert_one({"type": "Water Meter", "days": 730})
    meter = issuing["issue"]("Water Meter")
    scale = issuing["issue"]("Platform Scale")
    assert (meter["valid_until"] - meter["valid_from"]).days == 730 and meter["validity_days"] == 730
    assert (scale["valid_until"] - scale["valid_from"]).days == 365 and scale["validity_days"] == 365


def test_changing_a_rule_never_touches_an_existing_certificate(issuing):
    certs = issuing["db"]["certificates"]
    before = issuing["issue"]("Water Meter")
    issuing["db"]["validity_rules"].insert_one({"type": "Water Meter", "days": 90})
    stored = certs.find_one({"_id": before["_id"]})
    assert stored["validity_days"] == 365 and (stored["valid_until"] - stored["valid_from"]).days == 365
    after = issuing["issue"]("Water Meter")  # only certificates issued from now on follow the new rule
    assert after["validity_days"] == 90 and (after["valid_until"] - after["valid_from"]).days == 90
    assert certs.find_one({"_id": before["_id"]})["valid_until"] == stored["valid_until"]


# ------------------------------------------------------------------ the admin API


@pytest.fixture
def people(client):
    import app.config.db as dbmod

    def make(role, name):
        doc = {"name": name, "email": f"{name.lower()}@example.com", "role": role, "status": "active", "token_version": 0}
        if role in ("lmo", "gatc"):
            doc["jurisdiction"] = {"state_code": "WB", "district_code": "319"}
        doc["_id"] = dbmod.users_col.insert_one(doc).inserted_id
        return {"Authorization": f"Bearer {create_access_token(str(doc['_id']), 0)}"}

    return {role: make(role, role.title()) for role in ("owner", "lmo", "gatc", "admin")}


@pytest.mark.parametrize("method", ["get", "put", "delete"])
@pytest.mark.parametrize("who", ["owner", "lmo", "gatc", None])
def test_only_an_admin_may_use_the_validity_api(client, people, method, who):
    kwargs = {"headers": people[who]} if who else {}
    if method == "put":
        kwargs["json"] = {"days": 400}
    r = getattr(client, method)(f"{URL}" if method == "get" else f"{URL}/Water Meter", **kwargs)
    assert r.status_code in (401, 403)


def test_the_list_shows_every_instrument_type_with_the_default(client, people):
    from app.models.instrument import ALLOWED_INSTRUMENT_TYPES

    body = client.get(URL, headers=people["admin"]).json()
    assert [i["type"] for i in body["items"]] == ALLOWED_INSTRUMENT_TYPES
    assert (body["default_days"], body["default_label"]) == (365, "1 year")
    assert (body["min_days"], body["max_days"]) == (validity_service.MIN_VALIDITY_DAYS, validity_service.MAX_VALIDITY_DAYS)
    assert all(i["days"] == 365 and i["is_default"] and i["updated_at"] is None for i in body["items"])


def test_setting_and_resetting_a_rule(client, people):
    r = client.put(f"{URL}/Water Meter", headers=people["admin"], json={"days": 730})
    assert r.status_code == 200
    row = r.json()
    assert (row["type"], row["days"], row["label"], row["is_default"]) == ("Water Meter", 730, "2 years", False)
    assert row["updated_by_name"] == "Admin" and row["updated_at"]
    items = {i["type"]: i for i in client.get(URL, headers=people["admin"]).json()["items"]}
    assert items["Water Meter"]["days"] == 730 and items["Platform Scale"]["days"] == 365
    # Setting it again changes the one rule, it does not add a second.
    client.put(f"{URL}/Water Meter", headers=people["admin"], json={"days": 540})
    import app.config.db as dbmod

    assert dbmod.db["validity_rules"].count_documents({"type": "Water Meter"}) == 1
    back = client.delete(f"{URL}/Water Meter", headers=people["admin"])
    assert back.status_code == 200 and back.json()["days"] == 365 and back.json()["is_default"] is True
    assert dbmod.db["validity_rules"].count_documents({}) == 0


@pytest.mark.parametrize("days", [0, -5, validity_service.MIN_VALIDITY_DAYS - 1, validity_service.MAX_VALIDITY_DAYS + 1])
def test_a_period_outside_the_limits_is_refused(client, people, days):
    r = client.put(f"{URL}/Water Meter", headers=people["admin"], json={"days": days})
    assert r.status_code == 422
    import app.config.db as dbmod

    assert dbmod.db["validity_rules"].count_documents({}) == 0


def test_limits_are_accepted_at_the_edge(client, people):
    for days in (validity_service.MIN_VALIDITY_DAYS, validity_service.MAX_VALIDITY_DAYS):
        assert client.put(f"{URL}/Water Meter", headers=people["admin"], json={"days": days}).status_code == 200


def test_an_unknown_instrument_type_is_refused(client, people):
    assert client.put(f"{URL}/Spaceship", headers=people["admin"], json={"days": 400}).status_code == 404
    assert client.delete(f"{URL}/Spaceship", headers=people["admin"]).status_code == 404
    assert client.put(f"{URL}/Water Meter", headers=people["admin"], json={"days": "soon"}).status_code == 422


def test_changes_are_written_to_the_audit_trail(client, people):
    import app.config.db as dbmod

    client.put(f"{URL}/Water Meter", headers=people["admin"], json={"days": 730})
    client.delete(f"{URL}/Water Meter", headers=people["admin"])
    logs = {r["event"]: r for r in dbmod.db["audit_logs"].find({"event": {"$in": ["validity_rule_changed", "validity_rule_reset"]}})}
    assert logs["validity_rule_changed"]["detail"] == "type=Water Meter from=365 to=730"
    assert logs["validity_rule_reset"]["detail"] == "type=Water Meter from=730 to=365"


def test_owners_see_the_period_when_picking_a_type(client, people):
    client.put(f"{URL}/Water Meter", headers=people["admin"], json={"days": 730})
    specs = {s["type"]: s for s in client.get("/api/v1/instruments/meta/types", headers=people["owner"]).json()}
    assert (specs["Water Meter"]["validity_days"], specs["Water Meter"]["validity_label"]) == (730, "2 years")
    assert (specs["Platform Scale"]["validity_days"], specs["Platform Scale"]["validity_label"]) == (365, "1 year")
