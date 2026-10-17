"""POST /inspections: mandatory GPS location, identity method, access control, side effects."""
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from passlib.context import CryptContext

from app.config.inspection_forms import INSPECTION_FORMS, form_spec
from app.config.instrument_specs import INSTRUMENT_SPECS
from mfa_helpers import enroll_mfa, full_login

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
URL = "/api/v1/inspections"
GPS = {"lat": 24.1, "lng": 88.25, "accuracy_m": 12}
TYPE = "Electronic Weighing Machine"  # needs 3 test loads
_seals = iter(range(1, 10_000))


@pytest.fixture
def env(client, monkeypatch):
    """Patches the collections the inspection router imported by name, and the side effects."""
    import app.config.db as dbmod
    import app.routers.inspections as insp_mod
    import app.services.status_transition as st_mod

    monkeypatch.setattr(insp_mod, "inspections_col", dbmod.db["inspections"])
    monkeypatch.setattr(insp_mod, "applications_col", dbmod.db["applications"])
    monkeypatch.setattr(insp_mod, "instruments_col", dbmod.db["instruments"])
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
    return {"email": email, "password": "Old-Passw0rd!", "_id": doc["_id"], "role": role,
            "mfa_secret": enroll_mfa(doc["_id"])}


def _headers(client, creds):
    # One login per account per test: a TOTP code can't be reused inside its time window.
    if "_token" not in creds:
        if creds.get("role") == "owner":  # owners sign in with a password alone
            client.cookies.clear()
            creds["_token"] = client.post(
                "/api/v1/auth/login", json={"email": creds["email"], "password": creds["password"]}
            ).json()["token"]
        else:
            creds["_token"] = full_login(client, creds).json()["token"]
    return {"Authorization": f"Bearer {creds['_token']}"}


def _scheduled_app(env, officer_id, status="scheduled", owner_id=None, instrument_type=TYPE):
    instrument_id = env["db"]["instruments"].insert_one({"type": instrument_type, "uiid": "LM-26-TEST0001"}).inserted_id
    return env["db"]["applications"].insert_one({
        "owner_id": owner_id or ObjectId(), "instrument_id": instrument_id, "status": status,
        "assigned_officer_id": officer_id, "status_history": [],
        "created_at": datetime.now(timezone.utc),
    }).inserted_id


def _points(n=3):
    return [{"reference": 10.0 * (i + 1), "indicated": 10.0 * (i + 1) + 0.02} for i in range(n)]


def _all_ok(instrument_type=TYPE):
    return {c["key"]: True for c in form_spec(instrument_type)["checks"]}


def _body(app_id, **over):
    """A complete, valid submission: a Pass with test loads, every check ticked and a fresh seal number.
    A Fail carries no seal (none is fixed on a failed instrument)."""
    body = {"application_id": str(app_id), "observations": "Checked against standards", "result": "pass",
            "location": GPS, "test_points": _points(), "checks": _all_ok()}
    body.update(over)
    if body["result"] == "pass":
        body.setdefault("seal_number", f"SEAL-{next(_seals):05d}")
    return body


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


# ---- The detailed form: test points, checks, seal number ----

def _post(client, env, body_over=None, *, officer=None, app_kwargs=None):
    officer = officer or _seed_officer()
    app_id = _scheduled_app(env, officer["_id"], **(app_kwargs or {}))
    r = client.post(URL, json=_body(app_id, **(body_over or {})), headers=_headers(client, officer))
    return r, app_id, officer


def _untouched(env, app_id):
    assert env["db"]["inspections"].count_documents({}) == 0
    assert env["db"]["applications"].find_one({"_id": app_id})["status"] == "scheduled"
    assert env["notified"] == [] and env["generated"] == []


def test_every_instrument_type_has_a_form():
    assert set(INSPECTION_FORMS) == set(INSTRUMENT_SPECS), "add the new instrument type to inspection_forms.py"
    for t in INSTRUMENT_SPECS:
        spec = form_spec(t)
        keys = [c["key"] for c in spec["checks"]]
        assert len(keys) == len(set(keys)), t
        assert spec["test"]["unit"], t
        assert 1 <= spec["test"]["min_points"] <= spec["test"]["max_points"], t
        assert any(c["required"] for c in spec["checks"]), t


def test_form_spec_endpoint(client, env, registered_owner):
    officer = _seed_officer()
    h = _headers(client, officer)
    r = client.get(f"{URL}/form-spec", params={"type": "Fuel Dispensing Unit"}, headers=h)
    assert r.status_code == 200
    spec = r.json()
    assert spec["test"]["unit"] == "L" and spec["test"]["min_points"] == 2
    assert spec["seal"]["required_on_pass"] is True
    assert client.get(f"{URL}/form-spec", params={"type": "Spaceship"}, headers=h).status_code == 404
    assert client.get(f"{URL}/form-spec", params={"type": TYPE}).status_code in (401, 403)


def test_pass_stores_readings_with_error_checks_and_seal(client, env):
    r, app_id, officer = _post(client, env, {
        "test_points": [{"reference": 20, "indicated": 20.05}, {"reference": 0, "indicated": 0.01},
                        {"reference": 5, "indicated": 4.98}],
        "seal_number": "  wb/2026 0042 ",
    })
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["seal_number"] == "WB/2026 0042"  # trimmed, upper-cased
    pts = out["test_points"]
    assert pts[0]["error"] == pytest.approx(0.05) and pts[0]["error_pct"] == pytest.approx(0.25)
    assert pts[1]["error"] == pytest.approx(0.01) and pts[1]["error_pct"] is None  # zero reference
    assert pts[2]["error"] == pytest.approx(-0.02)
    assert all(c["ok"] for c in out["checks"]) and all(c["label"] for c in out["checks"])
    assert out["form"]["unit"] == "kg" and out["form"]["instrument_type"] == TYPE
    assert env["db"]["applications"].find_one({"_id": app_id})["status"] == "certified"


def test_pass_without_seal_number_is_rejected(client, env):
    officer = _seed_officer()
    app_id = _scheduled_app(env, officer["_id"])
    body = _body(app_id)
    del body["seal_number"]
    r = client.post(URL, json=body, headers=_headers(client, officer))
    assert r.status_code == 422 and "seal" in r.json()["detail"].lower()
    _untouched(env, app_id)


@pytest.mark.parametrize("seal", ["", "   ", "ab", "SEAL<script>", "X" * 40])
def test_bad_seal_numbers_are_rejected(client, env, seal):
    r, app_id, _ = _post(client, env, {"seal_number": seal})
    assert r.status_code == 422
    _untouched(env, app_id)


def test_pass_needs_the_minimum_number_of_test_readings(client, env):
    r, app_id, _ = _post(client, env, {"test_points": _points(2)})
    assert r.status_code == 422 and "at least 3" in r.json()["detail"]
    _untouched(env, app_id)


def test_pass_needs_every_check_answered(client, env):
    checks = _all_ok()
    checks.pop("no_tampering")
    r, app_id, _ = _post(client, env, {"checks": checks})
    assert r.status_code == 422 and "Answer every check" in r.json()["detail"]
    _untouched(env, app_id)


def test_pass_is_refused_while_a_required_check_is_not_met(client, env):
    r, app_id, _ = _post(client, env, {"checks": {**_all_ok(), "zero_ok": False}})
    assert r.status_code == 422 and "Fail instead" in r.json()["detail"]
    _untouched(env, app_id)


def test_unknown_check_and_out_of_range_readings_are_rejected(client, env):
    officer = _seed_officer()
    for over in (
        {"checks": {**_all_ok(), "made_up": True}},
        {"test_points": [{"reference": 1e12, "indicated": 1}] * 3},
        {"test_points": _points(13)},
    ):
        r, _, _ = _post(client, env, over, officer=officer)
        assert r.status_code == 422, over
    assert env["db"]["inspections"].count_documents({}) == 0


def test_fail_can_record_a_failed_check_and_readings_but_no_seal(client, env):
    r, app_id, _ = _post(client, env, {"result": "fail", "checks": {**_all_ok(), "no_tampering": False}})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["seal_number"] is None
    assert [c["ok"] for c in out["checks"] if c["key"] == "no_tampering"] == [False]
    assert env["db"]["applications"].find_one({"_id": app_id})["status"] == "rejected"


def test_fail_with_only_notes_is_still_accepted(client, env):
    officer = _seed_officer()
    app_id = _scheduled_app(env, officer["_id"])
    body = {"application_id": str(app_id), "observations": "Seal broken", "result": "fail", "location": GPS}
    r = client.post(URL, json=body, headers=_headers(client, officer))
    assert r.status_code == 201, r.text
    assert r.json()["test_points"] == [] and r.json()["form"] is None


def test_fail_with_a_seal_number_is_rejected(client, env):
    r, app_id, _ = _post(client, env, {"result": "fail", "seal_number": "SEAL-9999"})
    assert r.status_code == 422
    _untouched(env, app_id)


def test_each_instrument_type_uses_its_own_form(client, env):
    officer = _seed_officer()
    h = _headers(client, officer)
    app_id = _scheduled_app(env, officer["_id"], instrument_type="Fuel Dispensing Unit")
    spec = form_spec("Fuel Dispensing Unit")
    # The weighing-machine checks (e.g. zero_ok) are not on a fuel dispenser's form.
    bad = client.post(URL, json=_body(app_id, test_points=_points(2), checks=_all_ok(TYPE)), headers=h)
    assert bad.status_code == 422
    ok = client.post(URL, json=_body(app_id, test_points=_points(2), checks={c["key"]: True for c in spec["checks"]}), headers=h)
    assert ok.status_code == 201, ok.text
    assert ok.json()["form"]["unit"] == "L"


def test_a_seal_number_can_be_used_only_once(client, env):
    officer = _seed_officer()
    h = _headers(client, officer)
    first = _scheduled_app(env, officer["_id"])
    second = _scheduled_app(env, officer["_id"])
    assert client.post(URL, json=_body(first, seal_number="SEAL-DUP-1"), headers=h).status_code == 201
    r = client.post(URL, json=_body(second, seal_number=" seal-dup-1"), headers=h)
    assert r.status_code == 409 and "Seal number" in r.json()["detail"]
    assert env["db"]["applications"].find_one({"_id": second})["status"] == "scheduled"
    assert env["db"]["inspections"].count_documents({}) == 1


def test_old_form_without_details_is_refused_for_a_pass_and_accepted_when_not_strict(client, env, monkeypatch):
    from app.config import settings
    officer = _seed_officer()
    h = _headers(client, officer)
    app_id = _scheduled_app(env, officer["_id"])
    legacy = {"application_id": str(app_id), "observations": "ok", "result": "pass", "location": GPS}
    r = client.post(URL, json=legacy, headers=h)
    assert r.status_code == 422 and "out of date" in r.json()["detail"]
    _untouched(env, app_id)
    monkeypatch.setattr(settings, "INSPECTION_FORM_STRICT", False)
    r = client.post(URL, json=legacy, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["seal_number"] is None and r.json()["form"] is None


def test_replaying_a_queued_inspection_still_returns_the_original(client, env):
    officer = _seed_officer()
    h = _headers(client, officer)
    app_id = _scheduled_app(env, officer["_id"])
    body = _body(app_id, client_id="detail-form-1", seal_number="SEAL-REPLAY-1")
    first = client.post(URL, json=body, headers=h)
    again = client.post(URL, json=body, headers=h)
    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["seal_number"] == "SEAL-REPLAY-1"
    assert env["db"]["inspections"].count_documents({}) == 1


def test_inspection_by_application_visibility(client, env):
    officer = _seed_officer("a@example.com")
    other = _seed_officer("b@example.com")
    owner = _seed_officer("owner@example.com", role="owner")
    admin = _seed_officer("admin@example.com", role="admin")
    app_id = _scheduled_app(env, officer["_id"], owner_id=owner["_id"])
    assert client.post(URL, json=_body(app_id), headers=_headers(client, officer)).status_code == 201
    path = f"{URL}/by-application/{app_id}"

    mine = client.get(path, headers=_headers(client, officer)).json()
    assert mine["location"]["lat"] == 24.1 and mine["officer_id"]
    assert client.get(path, headers=_headers(client, admin)).json()["location"] is not None

    seen = client.get(path, headers=_headers(client, owner))
    assert seen.status_code == 200
    body = seen.json()
    assert body["officer_id"] is None and body["location"] is None  # no officer identity or GPS for the owner
    assert body["seal_number"] and len(body["test_points"]) == 3

    assert client.get(path, headers=_headers(client, other)).status_code == 403
    stranger = _seed_officer("stranger@example.com", role="owner")
    assert client.get(path, headers=_headers(client, stranger)).status_code == 403
    assert client.get(f"{URL}/by-application/{ObjectId()}", headers=_headers(client, admin)).status_code == 404
    assert client.get(f"{URL}/by-application/nope", headers=_headers(client, admin)).status_code == 400
