"""POST /inspections: mandatory GPS location, identity method, access control, side effects."""
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from passlib.context import CryptContext

from mfa_helpers import enroll_mfa, full_login

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
URL = "/api/v1/inspections"
GPS = {"lat": 24.1, "lng": 88.25, "accuracy_m": 12}


@pytest.fixture
def env(client, monkeypatch):
    """Patches the collections the inspection router imported by name, and the side effects."""
    import app.config.db as dbmod
    import app.routers.inspections as insp_mod
    import app.services.status_transition as st_mod

    monkeypatch.setattr(insp_mod, "inspections_col", dbmod.db["inspections"])
    monkeypatch.setattr(insp_mod, "applications_col", dbmod.db["applications"])
    monkeypatch.setattr(st_mod, "applications_col", dbmod.db["applications"])

    notified, generated = [], []
    monkeypatch.setattr(insp_mod, "notify_inspection_result", lambda app_doc, doc: notified.append(doc["result"]))
    monkeypatch.setattr(insp_mod, "start_certificate_generation", lambda oid: generated.append(oid))
    return {"db": dbmod.db, "notified": notified, "generated": generated}


def _seed_officer(email="lmo@example.com", role="lmo"):
    import app.config.db as dbmod

    doc = {"name": role, "email": email, "password": _pwd.hash("Old-Passw0rd!"), "role": role,
           "status": "active", "token_version": 0}
    doc["_id"] = dbmod.users_col.insert_one(doc).inserted_id
    return {"email": email, "password": "Old-Passw0rd!", "_id": doc["_id"], "mfa_secret": enroll_mfa(doc["_id"])}


def _headers(client, creds):
    return {"Authorization": f"Bearer {full_login(client, creds).json()['token']}"}


def _scheduled_app(env, officer_id, status="scheduled"):
    return env["db"]["applications"].insert_one({
        "owner_id": ObjectId(), "instrument_id": ObjectId(), "status": status,
        "assigned_officer_id": officer_id, "status_history": [],
        "created_at": datetime.now(timezone.utc),
    }).inserted_id


def _body(app_id, **over):
    return {"application_id": str(app_id), "observations": "Checked against standards", "result": "pass",
            "location": GPS, **over}


def test_location_is_mandatory(client, env):
    officer = _seed_officer()
    app_id = _scheduled_app(env, officer["_id"])
    body = _body(app_id)
    del body["location"]
    r = client.post(URL, json=body, headers=_headers(client, officer))
    assert r.status_code == 422
    assert env["db"]["inspections"].count_documents({}) == 0
    assert env["db"]["applications"].find_one({"_id": app_id})["status"] == "scheduled"


def test_null_location_is_rejected(client, env):
    officer = _seed_officer()
    app_id = _scheduled_app(env, officer["_id"])
    r = client.post(URL, json=_body(app_id, location=None), headers=_headers(client, officer))
    assert r.status_code == 422


@pytest.mark.parametrize("bad", [
    {"lat": 91, "lng": 0},
    {"lat": -91, "lng": 0},
    {"lat": 0, "lng": 181},
    {"lat": 0, "lng": -181},
    {"lat": 0},
    {"lat": 0, "lng": 0, "accuracy_m": -1},
    {"lat": "north", "lng": 0},
])
def test_invalid_coordinates_are_rejected(client, env, bad):
    officer = _seed_officer()
    app_id = _scheduled_app(env, officer["_id"])
    r = client.post(URL, json=_body(app_id, location=bad), headers=_headers(client, officer))
    assert r.status_code == 422
    assert env["db"]["inspections"].count_documents({}) == 0


def test_valid_submission_stores_location_and_identity_method(client, env):
    officer = _seed_officer()
    app_id = _scheduled_app(env, officer["_id"])
    r = client.post(URL, json=_body(app_id, identity_method="qr"), headers=_headers(client, officer))
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["identity_method"] == "qr"
    assert out["location"] == {"lat": 24.1, "lng": 88.25, "accuracy_m": 12.0}

    stored = env["db"]["inspections"].find_one({"application_id": app_id})
    assert stored["location"]["lat"] == 24.1 and stored["identity_method"] == "qr"
    assert env["db"]["applications"].find_one({"_id": app_id})["status"] == "certified"
    assert env["notified"] == ["pass"] and len(env["generated"]) == 1


def test_identity_method_defaults_to_manual_and_rejects_unknown(client, env):
    officer = _seed_officer()
    headers = _headers(client, officer)
    app_id = _scheduled_app(env, officer["_id"])
    r = client.post(URL, json=_body(app_id, identity_method="telepathy"), headers=headers)
    assert r.status_code == 422
    r = client.post(URL, json=_body(app_id), headers=headers)
    assert r.status_code == 201
    assert r.json()["identity_method"] == "manual"


def test_accuracy_is_optional(client, env):
    officer = _seed_officer()
    app_id = _scheduled_app(env, officer["_id"])
    r = client.post(URL, json=_body(app_id, location={"lat": 22.57, "lng": 88.36}), headers=_headers(client, officer))
    assert r.status_code == 201
    assert r.json()["location"]["accuracy_m"] is None


def test_fail_result_rejects_application_and_issues_no_certificate(client, env):
    officer = _seed_officer()
    app_id = _scheduled_app(env, officer["_id"])
    r = client.post(URL, json=_body(app_id, result="fail"), headers=_headers(client, officer))
    assert r.status_code == 201
    assert env["db"]["applications"].find_one({"_id": app_id})["status"] == "rejected"
    assert env["generated"] == []


def test_only_the_assigned_officer_can_submit(client, env):
    owner_of_job = _seed_officer("a@example.com")
    other = _seed_officer("b@example.com")
    app_id = _scheduled_app(env, owner_of_job["_id"])
    r = client.post(URL, json=_body(app_id), headers=_headers(client, other))
    assert r.status_code == 403
    assert env["db"]["inspections"].count_documents({}) == 0


def test_application_must_be_scheduled(client, env):
    officer = _seed_officer()
    app_id = _scheduled_app(env, officer["_id"], status="submitted")
    r = client.post(URL, json=_body(app_id), headers=_headers(client, officer))
    assert r.status_code == 409


def test_unknown_and_malformed_application_ids(client, env):
    officer = _seed_officer()
    headers = _headers(client, officer)
    assert client.post(URL, json=_body(ObjectId()), headers=headers).status_code == 404
    assert client.post(URL, json=_body("not-an-id"), headers=headers).status_code == 400


def test_requires_authentication_and_officer_role(client, env, registered_owner):
    assert client.post(URL, json=_body(ObjectId())).status_code in (401, 403)


def test_get_inspection_returns_location_to_its_officer_only(client, env):
    officer = _seed_officer("a@example.com")
    other = _seed_officer("b@example.com")
    app_id = _scheduled_app(env, officer["_id"])
    created = client.post(URL, json=_body(app_id), headers=_headers(client, officer)).json()
    mine = client.get(f"{URL}/{created['id']}", headers=_headers(client, officer))
    assert mine.status_code == 200 and mine.json()["location"]["lng"] == 88.25
    assert client.get(f"{URL}/{created['id']}", headers=_headers(client, other)).status_code == 403


def test_legacy_inspection_without_location_still_readable(client, env):
    officer = _seed_officer()
    app_id = _scheduled_app(env, officer["_id"])
    legacy = env["db"]["inspections"].insert_one({
        "application_id": app_id, "officer_id": officer["_id"], "observations": "old", "result": "pass",
        "photos": [], "inspected_at": datetime.now(timezone.utc),
    }).inserted_id
    r = client.get(f"{URL}/{legacy}", headers=_headers(client, officer))
    assert r.status_code == 200
    assert r.json()["location"] is None and r.json()["identity_method"] == "manual"


# ---- Offline sync: idempotency (client_id) and capture time (captured_at) ----

def test_replayed_client_id_returns_original_and_applies_once(client, env):
    officer = _seed_officer()
    app_id = _scheduled_app(env, officer["_id"])
    h = _headers(client, officer)
    first = client.post(URL, json=_body(app_id, client_id="abc12345-uuid"), headers=h)
    assert first.status_code == 201, first.text
    # The application is now 'certified', so without idempotency this retry would be a 409.
    again = client.post(URL, json=_body(app_id, client_id="abc12345-uuid"), headers=h)
    assert again.status_code == 200, again.text
    assert again.json()["id"] == first.json()["id"]
    assert env["db"]["inspections"].count_documents({}) == 1
    assert env["notified"] == ["pass"] and len(env["generated"]) == 1


def test_without_client_id_a_repeat_is_still_a_conflict(client, env):
    officer = _seed_officer()
    app_id = _scheduled_app(env, officer["_id"])
    h = _headers(client, officer)
    assert client.post(URL, json=_body(app_id), headers=h).status_code == 201
    assert client.post(URL, json=_body(app_id), headers=h).status_code == 409


def test_client_id_is_scoped_to_the_officer(client, env):
    a = _seed_officer("a@example.com")
    b = _seed_officer("b@example.com")
    app_a = _scheduled_app(env, a["_id"])
    app_b = _scheduled_app(env, b["_id"])
    assert client.post(URL, json=_body(app_a, client_id="shared-id-1234"), headers=_headers(client, a)).status_code == 201
    # Another officer reusing the id gets their own record, never the first officer's.
    r = client.post(URL, json=_body(app_b, client_id="shared-id-1234"), headers=_headers(client, b))
    assert r.status_code == 201
    assert env["db"]["inspections"].count_documents({}) == 2


@pytest.mark.parametrize("bad", ["short", "has space in it", "x" * 65, "bad/chars!!"])
def test_invalid_client_id_is_rejected(client, env, bad):
    officer = _seed_officer()
    app_id = _scheduled_app(env, officer["_id"])
    r = client.post(URL, json=_body(app_id, client_id=bad), headers=_headers(client, officer))
    assert r.status_code == 422


def test_captured_at_is_used_as_inspection_time_and_flagged_offline(client, env):
    from datetime import timedelta
    officer = _seed_officer()
    app_id = _scheduled_app(env, officer["_id"])
    captured = datetime.now(timezone.utc) - timedelta(hours=5)
    r = client.post(URL, json=_body(app_id, captured_at=captured.isoformat()), headers=_headers(client, officer))
    assert r.status_code == 201, r.text
    assert r.json()["submitted_offline"] is True
    stored = env["db"]["inspections"].find_one({"application_id": app_id})
    assert abs((stored["inspected_at"].replace(tzinfo=timezone.utc) - captured).total_seconds()) < 2
    assert stored["received_at"] > stored["inspected_at"]


@pytest.mark.parametrize("delta_hours", [24, -24 * 30])
def test_implausible_captured_at_falls_back_to_server_time(client, env, delta_hours):
    from datetime import timedelta
    officer = _seed_officer()
    app_id = _scheduled_app(env, officer["_id"])
    bogus = datetime.now(timezone.utc) + timedelta(hours=delta_hours)  # future, or older than the window
    r = client.post(URL, json=_body(app_id, captured_at=bogus.isoformat()), headers=_headers(client, officer))
    assert r.status_code == 201, r.text
    assert r.json()["submitted_offline"] is False
    stored = env["db"]["inspections"].find_one({"application_id": app_id})
    assert abs((stored["inspected_at"].replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).total_seconds()) < 30
