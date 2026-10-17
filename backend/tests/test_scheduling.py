"""#5 Inspection scheduling: claim with date + slot, reschedule, admin assign, availability, emails."""
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from passlib.context import CryptContext

from app.services import email_templates, scheduling
from mfa_helpers import enroll_mfa, full_login

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
BASE = "/api/v1/applications"
WB_319 = {"state_code": "WB", "district_code": "319"}


def _day(offset: int = 3, *, sunday: bool = False) -> str:
    """A bookable India date at least `offset` days ahead (never a Sunday unless asked)."""
    d = scheduling.today_ist() + timedelta(days=offset)
    while (d.weekday() == 6) != sunday:
        d += timedelta(days=1)
    return d.isoformat()


@pytest.fixture
def env(client, monkeypatch):
    import app.config.db as dbmod
    import app.routers.applications as apps_mod

    monkeypatch.setattr(apps_mod, "applications_col", dbmod.db["applications"])
    monkeypatch.setattr(apps_mod, "users_col", dbmod.db["users"])
    sent = {"scheduled": [], "rescheduled": []}
    monkeypatch.setattr(apps_mod, "notify_application_scheduled", lambda doc: sent["scheduled"].append(doc))
    monkeypatch.setattr(
        apps_mod, "notify_application_rescheduled",
        lambda doc, **kw: sent["rescheduled"].append({"doc": doc, **kw}),
    )
    return {"db": dbmod.db, "sent": sent, "mod": apps_mod}


def _seed_user(email, role, jurisdiction=None, status="active"):
    import app.config.db as dbmod

    doc = {"name": email, "email": email, "password": _pwd.hash("Old-Passw0rd!"), "role": role,
           "status": status, "token_version": 0}
    if jurisdiction:
        doc["jurisdiction"] = dict(jurisdiction)
    doc["_id"] = dbmod.users_col.insert_one(doc).inserted_id
    return {"email": email, "password": "Old-Passw0rd!", "_id": doc["_id"], "mfa_secret": enroll_mfa(doc["_id"])}


def _h(client, creds):
    return {"Authorization": f"Bearer {full_login(client, creds).json()['token']}"}


def _submitted(env, **over):
    doc = {"owner_id": ObjectId(), "instrument_id": ObjectId(), "status": "submitted",
           "assigned_officer_id": None, "submitted_at": datetime.now(timezone.utc),
           "state_code": "WB", "district_code": "319", "history": [], **over}
    return env["db"]["applications"].insert_one(doc).inserted_id


def _claim(client, headers, app_id, day=None, slot="morning"):
    return client.post(f"{BASE}/{app_id}/claim", json={"date": day or _day(), "slot": slot}, headers=headers)


def _stored(env, app_id):
    return env["db"]["applications"].find_one({"_id": app_id})


# ---------------------------------------------------------------- claim

def test_claim_books_date_and_slot(client, env):
    lmo = _seed_user("lmo@example.com", "lmo", WB_319)
    app_id = _submitted(env)
    day = _day()
    r = _claim(client, _h(client, lmo), app_id, day, "afternoon")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "scheduled" and body["scheduled_date"] == day and body["slot"] == "afternoon"
    assert "2:00 PM" in body["slot_label"]
    assert [h["kind"] for h in body["schedule_history"]] == ["scheduled"]
    assert len(env["sent"]["scheduled"]) == 1
    assert _stored(env, app_id)["assigned_officer_id"] == lmo["_id"]


def test_claim_without_date_and_slot_is_422_and_changes_nothing(client, env):
    lmo = _seed_user("lmo@example.com", "lmo", WB_319)
    app_id = _submitted(env)
    r = client.post(f"{BASE}/{app_id}/claim", headers=_h(client, lmo))
    assert r.status_code == 422
    assert _stored(env, app_id)["status"] == "submitted"


@pytest.mark.parametrize("make_body, expect", [
    (lambda: {"date": _day(sunday=True), "slot": "morning"}, "Sunday"),
    (lambda: {"date": (scheduling.today_ist() - timedelta(days=1)).isoformat(), "slot": "morning"}, "passed"),
    (lambda: {"date": _day(), "slot": "evening"}, "Slot must be"),
    (lambda: {"date": "02-11-2026", "slot": "morning"}, "YYYY-MM-DD"),
    (lambda: {"date": (scheduling.today_ist() + timedelta(days=400)).isoformat(), "slot": "morning"}, "days ahead"),
])
def test_bad_date_or_slot_is_422_and_nothing_written(client, env, make_body, expect):
    lmo = _seed_user("lmo@example.com", "lmo", WB_319)
    app_id = _submitted(env)
    r = client.post(f"{BASE}/{app_id}/claim", json=make_body(), headers=_h(client, lmo))
    assert r.status_code == 422 and expect in r.text
    assert _stored(env, app_id)["status"] == "submitted"
    assert not env["sent"]["scheduled"]


def test_officer_slot_capacity_is_enforced_per_slot(client, env, monkeypatch):
    monkeypatch.setattr(scheduling.settings, "SLOT_CAPACITY_PER_OFFICER", 2)
    lmo = _seed_user("lmo@example.com", "lmo", WB_319)
    h = _h(client, lmo)
    day = _day()
    a, b, c = _submitted(env), _submitted(env), _submitted(env)
    assert _claim(client, h, a, day).status_code == 200
    assert _claim(client, h, b, day).status_code == 200
    full = _claim(client, h, c, day)
    assert full.status_code == 409 and "full" in full.text
    assert _stored(env, c)["status"] == "submitted"
    assert _claim(client, h, c, day, "afternoon").status_code == 200  # other slot is free


def test_capacity_is_per_officer(client, env, monkeypatch):
    monkeypatch.setattr(scheduling.settings, "SLOT_CAPACITY_PER_OFFICER", 1)
    one = _seed_user("one@example.com", "lmo", WB_319)
    two = _seed_user("two@example.com", "lmo", WB_319)
    day = _day()
    assert _claim(client, _h(client, one), _submitted(env), day).status_code == 200
    assert _claim(client, _h(client, two), _submitted(env), day).status_code == 200


def test_claim_outside_jurisdiction_is_403_and_nothing_written(client, env):
    lmo = _seed_user("lmo@example.com", "lmo", {"state_code": "WB", "district_code": "999"})
    app_id = _submitted(env)
    assert _claim(client, _h(client, lmo), app_id).status_code == 403
    assert _stored(env, app_id)["assigned_officer_id"] is None


def test_second_officer_cannot_claim_a_claimed_application(client, env):
    one = _seed_user("one@example.com", "lmo", WB_319)
    two = _seed_user("two@example.com", "lmo", WB_319)
    app_id = _submitted(env)
    assert _claim(client, _h(client, one), app_id).status_code == 200
    assert _claim(client, _h(client, two), app_id).status_code == 409


def test_losing_a_race_for_the_last_place_undoes_the_claim(client, env, monkeypatch):
    lmo = _seed_user("lmo@example.com", "lmo", WB_319)
    app_id = _submitted(env)
    monkeypatch.setattr(scheduling, "slot_still_within_capacity", lambda *a, **k: False)
    r = _claim(client, _h(client, lmo), app_id)
    assert r.status_code == 409 and "just filled" in r.text
    doc = _stored(env, app_id)
    assert doc["status"] == "submitted" and doc["assigned_officer_id"] is None
    assert doc["scheduled_date"] is None and doc["history"] == [] and doc["schedule_history"] == []


# ---------------------------------------------------------------- reschedule

def _booked(client, env, officer, day=None, slot="morning"):
    app_id = _submitted(env)
    assert _claim(client, _h(client, officer), app_id, day, slot).status_code == 200
    return app_id


def test_assigned_officer_can_reschedule_and_history_keeps_the_old_slot(client, env):
    lmo = _seed_user("lmo@example.com", "lmo", WB_319)
    first, second = _day(3), _day(5)
    app_id = _booked(client, env, lmo, first, "morning")
    r = client.post(f"{BASE}/{app_id}/schedule", headers=_h(client, lmo),
                    json={"date": second, "slot": "afternoon", "reason": "Court hearing"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["scheduled_date"], body["slot"]) == (second, "afternoon")
    last = body["schedule_history"][-1]
    assert last["kind"] == "rescheduled" and last["previous_date"] == first and last["previous_slot"] == "morning"
    assert last["reason"] == "Court hearing" and len(body["schedule_history"]) == 2
    note = env["sent"]["rescheduled"][0]
    assert note["previous_date"] == first and note["reason"] == "Court hearing"
    assert body["status"] == "scheduled"  # status does not change


def test_reschedule_to_same_slot_is_409(client, env):
    lmo = _seed_user("lmo@example.com", "lmo", WB_319)
    day = _day()
    app_id = _booked(client, env, lmo, day, "morning")
    assert client.post(f"{BASE}/{app_id}/schedule", headers=_h(client, lmo),
                       json={"date": day, "slot": "morning"}).status_code == 409


def test_reschedule_into_a_full_slot_is_409_but_own_place_does_not_count(client, env, monkeypatch):
    monkeypatch.setattr(scheduling.settings, "SLOT_CAPACITY_PER_OFFICER", 1)
    lmo = _seed_user("lmo@example.com", "lmo", WB_319)
    h = _h(client, lmo)
    d1, d2 = _day(3), _day(5)
    a = _booked(client, env, lmo, d1, "morning")
    _booked(client, env, lmo, d2, "morning")
    assert client.post(f"{BASE}/{a}/schedule", headers=h, json={"date": d2, "slot": "morning"}).status_code == 409
    # capacity 1 and the only booking in d1/afternoon is none: moving there works
    assert client.post(f"{BASE}/{a}/schedule", headers=h, json={"date": d1, "slot": "afternoon"}).status_code == 200


def test_only_assigned_officer_or_admin_can_reschedule(client, env):
    owner_officer = _seed_user("a@example.com", "lmo", WB_319)
    other = _seed_user("b@example.com", "lmo", WB_319)
    admin = _seed_user("admin@example.com", "admin")
    app_id = _booked(client, env, owner_officer)
    body = {"date": _day(6), "slot": "afternoon"}
    assert client.post(f"{BASE}/{app_id}/schedule", headers=_h(client, other), json=body).status_code == 403
    assert client.post(f"{BASE}/{app_id}/schedule", headers=_h(client, admin), json=body).status_code == 200


def test_cannot_reschedule_unclaimed_or_inspected_applications(client, env):
    lmo = _seed_user("lmo@example.com", "lmo", WB_319)
    h = _h(client, lmo)
    body = {"date": _day(6), "slot": "morning"}
    unclaimed = _submitted(env)
    assert client.post(f"{BASE}/{unclaimed}/schedule", headers=h, json=body).status_code == 403
    done = _booked(client, env, lmo)
    env["db"]["applications"].update_one({"_id": done}, {"$set": {"status": "inspected"}})
    assert client.post(f"{BASE}/{done}/schedule", headers=h, json=body).status_code == 409


# ---------------------------------------------------------------- admin assign

def test_admin_assigns_a_submitted_application(client, env):
    admin = _seed_user("admin@example.com", "admin")
    lmo = _seed_user("lmo@example.com", "lmo", WB_319)
    app_id = _submitted(env)
    day = _day()
    r = client.post(f"{BASE}/{app_id}/assign", headers=_h(client, admin),
                    json={"officer_id": str(lmo["_id"]), "date": day, "slot": "morning"})
    assert r.status_code == 200, r.text
    doc = _stored(env, app_id)
    assert doc["status"] == "scheduled" and doc["assigned_officer_id"] == lmo["_id"] and doc["scheduled_date"] == day
    assert doc["schedule_history"][0]["kind"] == "assigned" and doc["history"][-1]["to"] == "scheduled"
    assert len(env["sent"]["scheduled"]) == 1


def test_admin_can_move_a_scheduled_application_to_another_officer(client, env):
    admin = _seed_user("admin@example.com", "admin")
    one = _seed_user("one@example.com", "lmo", WB_319)
    two = _seed_user("two@example.com", "lmo", WB_319)
    app_id = _booked(client, env, one)
    r = client.post(f"{BASE}/{app_id}/assign", headers=_h(client, admin),
                    json={"officer_id": str(two["_id"]), "date": _day(7), "slot": "afternoon", "reason": "Officer on leave"})
    assert r.status_code == 200, r.text
    doc = _stored(env, app_id)
    assert doc["assigned_officer_id"] == two["_id"] and doc["status"] == "scheduled"
    assert doc["schedule_history"][-1]["kind"] == "reassigned"
    assert len(env["sent"]["rescheduled"]) == 1 and len(env["sent"]["scheduled"]) == 1  # one from the claim


@pytest.mark.parametrize("officer_kwargs, code", [
    ({"jurisdiction": {"state_code": "WB", "district_code": "999"}}, 422),   # wrong district
    ({"jurisdiction": {"state_code": "BR", "district_code": "319"}}, 422),   # wrong state
    ({"jurisdiction": WB_319, "status": "pending"}, 409),                    # not active
])
def test_assign_checks_jurisdiction_and_active_account(client, env, officer_kwargs, code):
    admin = _seed_user("admin@example.com", "admin")
    lmo = _seed_user("lmo@example.com", "lmo", **officer_kwargs)
    app_id = _submitted(env)
    r = client.post(f"{BASE}/{app_id}/assign", headers=_h(client, admin),
                    json={"officer_id": str(lmo["_id"]), "date": _day(), "slot": "morning"})
    assert r.status_code == code
    assert _stored(env, app_id)["status"] == "submitted"


def test_gatc_can_be_assigned_anywhere_in_their_state(client, env):
    admin = _seed_user("admin@example.com", "admin")
    gatc = _seed_user("gatc@example.com", "gatc", {"state_code": "WB", "district_code": None})
    app_id = _submitted(env)
    r = client.post(f"{BASE}/{app_id}/assign", headers=_h(client, admin),
                    json={"officer_id": str(gatc["_id"]), "date": _day(), "slot": "morning"})
    assert r.status_code == 200, r.text


def test_assign_respects_capacity_and_is_admin_only(client, env, monkeypatch):
    monkeypatch.setattr(scheduling.settings, "SLOT_CAPACITY_PER_OFFICER", 1)
    admin = _seed_user("admin@example.com", "admin")
    lmo = _seed_user("lmo@example.com", "lmo", WB_319)
    day = _day()
    _booked(client, env, lmo, day, "morning")
    app_id = _submitted(env)
    body = {"officer_id": str(lmo["_id"]), "date": day, "slot": "morning"}
    assert client.post(f"{BASE}/{app_id}/assign", headers=_h(client, admin), json=body).status_code == 409
    assert client.post(f"{BASE}/{app_id}/assign", headers=_h(client, lmo), json=body).status_code == 403


# ---------------------------------------------------------------- availability

def test_slot_availability_counts_bookings_and_marks_sundays_closed(client, env, monkeypatch):
    monkeypatch.setattr(scheduling.settings, "SLOT_CAPACITY_PER_OFFICER", 3)
    lmo = _seed_user("lmo@example.com", "lmo", WB_319)
    day = _day()
    _booked(client, env, lmo, day, "morning")
    r = client.get(f"{BASE}/slots", params={"start": scheduling.today_ist().isoformat(), "days": 14}, headers=_h(client, lmo))
    assert r.status_code == 200, r.text
    days = {d["date"]: d for d in r.json()["days"]}
    morning = next(s for s in days[day]["slots"] if s["slot"] == "morning")
    assert (morning["booked"], morning["capacity"], morning["available"]) == (1, 3, 2)
    sunday = next(d for d in days.values() if date_is_sunday(d["date"]))
    assert sunday["bookable"] is False and all(s["available"] == 0 for s in sunday["slots"])


def date_is_sunday(s: str) -> bool:
    return datetime.strptime(s, "%Y-%m-%d").weekday() == 6


def test_officer_cannot_view_another_officers_diary_but_admin_can(client, env):
    one = _seed_user("one@example.com", "lmo", WB_319)
    two = _seed_user("two@example.com", "lmo", WB_319)
    admin = _seed_user("admin@example.com", "admin")
    assert client.get(f"{BASE}/slots", params={"officer_id": str(two["_id"])}, headers=_h(client, one)).status_code == 403
    assert client.get(f"{BASE}/slots", headers=_h(client, admin)).status_code == 422
    assert client.get(f"{BASE}/slots", params={"officer_id": str(two["_id"])}, headers=_h(client, admin)).status_code == 200


# ---------------------------------------------------------------- emails

CTX = {
    "owner_name": "Asha", "application_id": "A1", "application_url": "https://x/a",
    "instrument": {"type": "Platform Scale", "uiid": "LM-1", "manufacturer": "Acme", "model": "M", "serial_no": "S"},
}


def test_scheduled_email_shows_the_booked_date_and_slot():
    subject, text, html = email_templates.render(
        "application_scheduled", {**CTX, "scheduled_date": "2026-11-02", "slot_label": "Morning (10:00 AM - 1:00 PM)"})
    assert "02 Nov 2026" in subject and "Morning" in text and "Morning" in html


def test_scheduled_email_still_renders_without_a_schedule():
    subject, _, _ = email_templates.render("application_scheduled", CTX)
    assert "LM-1" in subject


def test_rescheduled_email_shows_new_and_old_slot_and_escapes_the_reason():
    subject, text, html = email_templates.render("inspection_rescheduled", {
        **CTX, "scheduled_date": "2026-11-04", "slot_label": "Afternoon (2:00 PM - 5:00 PM)",
        "previous_slot_text": "2026-11-02, Morning", "reason": "<script>x</script>"})
    assert "04 Nov 2026" in subject and "2026-11-02" in text and "<script>" not in html and "&lt;script&gt;" in html


# ---------------------------------------------------------------- pure rules

def test_slot_window_is_india_time():
    start, end = scheduling.slot_window("2026-11-02", "afternoon")
    assert (start.hour, end.hour) == (14, 17) and start.utcoffset() == timedelta(hours=5, minutes=30)
