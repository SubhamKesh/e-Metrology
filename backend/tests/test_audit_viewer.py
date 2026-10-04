"""Admin audit-log viewer: access control, filters, pagination, read-only."""
import ast
import pathlib
from datetime import datetime, timedelta, timezone

import pytest
from passlib.context import CryptContext

from app.services.audit import AUDIT_OUTCOMES, KNOWN_AUDIT_EVENTS
from mfa_helpers import enroll_mfa, full_login

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
URL = "/api/v1/admin/audit-logs"
T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def no_real_email(client, monkeypatch):
    import app.services.mailer as mailer_mod

    monkeypatch.setattr(mailer_mod, "send_email", lambda to, subject, body, html=None, sender=None: True)


def _seed(role, email, mfa=True) -> dict:
    import app.config.db as dbmod

    doc = {"name": role, "email": email, "password": _pwd.hash("Old-Passw0rd!"), "role": role,
           "status": "active", "token_version": 0}
    doc["_id"] = dbmod.users_col.insert_one(doc).inserted_id
    creds = {"email": email, "password": "Old-Passw0rd!", "_id": doc["_id"]}
    if mfa and role != "owner":
        creds["mfa_secret"] = enroll_mfa(doc["_id"])
    return creds


def _admin_headers(client):
    admin = _seed("admin", "boss@example.com")
    return {"Authorization": f"Bearer {full_login(client, admin).json()['token']}"}


def _rec(event, minutes=0, outcome="success", **extra):
    import app.config.db as dbmod

    dbmod.db["audit_logs"].insert_one({
        "event": event, "outcome": outcome, "email": None, "user_id": None, "role": None,
        "actor_id": None, "actor_email": None, "ip": "203.0.113.5", "user_agent": "pytest", "detail": None,
        "created_at": T0 + timedelta(minutes=minutes), **extra,
    })


def _get(client, headers, **params):
    return client.get(URL, headers=headers, params=params)


# ------------------------------------------------------------ access control


def test_only_admins_can_read_the_audit_log(client):
    admin_h = _admin_headers(client)
    assert _get(client, admin_h).status_code == 200

    officer = _seed("lmo", "off@example.com")
    owner = _seed("owner", "biz@example.com")
    officer_h = {"Authorization": f"Bearer {full_login(client, officer).json()['token']}"}
    owner_h = {"Authorization": "Bearer " + client.post("/api/v1/auth/login", json={"email": owner["email"], "password": owner["password"]}).json()["token"]}
    assert _get(client, officer_h).status_code == 403
    assert _get(client, owner_h).status_code == 403
    assert client.get(URL).status_code in (401, 403)


def test_the_audit_log_is_read_only_through_the_api(client):
    h = _admin_headers(client)
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)(URL, headers=h).status_code == 405
    # no per-record routes either
    assert client.delete(f"{URL}/64b000000000000000000000", headers=h).status_code in (404, 405)


# ---------------------------------------------------------------- listing


def test_lists_newest_first_with_every_field(client):
    h = _admin_headers(client)
    _rec("login_failed", 0, "failure", email="a@example.com", role="owner", detail="wrong_password")
    _rec("login_success", 5, email="a@example.com", role="owner")
    body = _get(client, h).json()
    # includes the admin's own login events from the fixture, newest first
    times = [i["created_at"] for i in body["items"]]
    assert times == sorted(times, reverse=True)
    item = next(i for i in body["items"] if i["event"] == "login_failed")
    assert item["email"] == "a@example.com" and item["role"] == "owner" and item["detail"] == "wrong_password"
    assert item["outcome"] == "failure" and item["ip"] == "203.0.113.5" and item["id"]
    assert body["events"] == list(KNOWN_AUDIT_EVENTS)


def test_timestamps_carry_a_timezone(client):
    h = _admin_headers(client)
    _rec("logout")
    stamp = next(i for i in _get(client, h, event="logout").json()["items"])["created_at"]
    assert stamp.endswith("Z") or stamp.endswith("+00:00")


def test_pagination(client):
    h = _admin_headers(client)
    for i in range(7):
        _rec("logout", i, email=f"u{i}@example.com")
    p1 = _get(client, h, event="logout", page_size=3, page=1).json()
    p2 = _get(client, h, event="logout", page_size=3, page=2).json()
    p3 = _get(client, h, event="logout", page_size=3, page=3).json()
    assert p1["total"] == p2["total"] == p3["total"] == 7
    assert [len(p["items"]) for p in (p1, p2, p3)] == [3, 3, 1]
    emails = [i["email"] for p in (p1, p2, p3) for i in p["items"]]
    assert emails == [f"u{i}@example.com" for i in range(6, -1, -1)]   # newest first, no repeats or gaps
    assert _get(client, h, event="logout", page_size=3, page=9).json()["items"] == []


def test_page_size_is_capped(client):
    h = _admin_headers(client)
    assert _get(client, h, page_size=101).status_code == 422
    assert _get(client, h, page_size=0).status_code == 422
    assert _get(client, h, page=0).status_code == 422


# ----------------------------------------------------------------- filters


def test_filter_by_event_outcome_and_role(client):
    h = _admin_headers(client)
    _rec("login_failed", 1, "failure", role="owner", email="o@example.com")
    _rec("login_failed", 2, "blocked", role="lmo", email="l@example.com")
    _rec("login_success", 3, role="owner", email="o@example.com")

    only_failed = _get(client, h, event="login_failed").json()
    assert only_failed["total"] == 2 and {i["event"] for i in only_failed["items"]} == {"login_failed"}
    assert _get(client, h, event="login_failed", outcome="blocked").json()["total"] == 1
    assert _get(client, h, event="login_failed", role="owner").json()["items"][0]["email"] == "o@example.com"
    assert _get(client, h, event="login_failed", outcome="blocked", role="owner").json()["total"] == 0


def test_unknown_filter_values_are_rejected(client):
    h = _admin_headers(client)
    assert _get(client, h, event="drop_database").status_code == 400
    assert _get(client, h, outcome="maybe").status_code == 422
    assert _get(client, h, role="wizard").status_code == 422


def test_search_matches_account_or_actor_email_case_insensitively(client):
    h = _admin_headers(client)
    _rec("account_suspended", 1, email="Officer.One@Example.com", role="lmo", actor_email="boss@example.com")
    _rec("login_failed", 2, "failure", email="someone.else@example.com")

    assert _get(client, h, search="officer.one").json()["total"] == 1       # substring, any case
    assert _get(client, h, search="OFFICER.ONE@EXAMPLE").json()["total"] == 1
    by_actor = _get(client, h, event="account_suspended", search="boss@").json()
    assert by_actor["total"] == 1 and by_actor["items"][0]["actor_email"] == "boss@example.com"
    assert _get(client, h, search="nobody@").json()["total"] == 0


def test_search_text_is_matched_literally_not_as_a_pattern(client):
    h = _admin_headers(client)
    _rec("login_failed", 1, "failure", email="a.b@example.com")
    _rec("login_failed", 2, "failure", email="axb@example.com")
    assert _get(client, h, search="a.b").json()["total"] == 1       # '.' is a dot, not "any character"
    assert _get(client, h, search=".*").json()["total"] == 0
    assert _get(client, h, search="(").status_code == 200           # would be a regex error if interpreted


def test_date_range_is_inclusive_on_both_days(client):
    h = _admin_headers(client)
    day = lambda d, hh=12: datetime(2026, 9, d, hh, tzinfo=timezone.utc)  # noqa: E731
    import app.config.db as dbmod

    for d, hh in ((9, 23), (10, 0), (10, 12), (11, 23), (12, 0)):
        dbmod.db["audit_logs"].insert_one({"event": "logout", "outcome": "success", "created_at": day(d, hh), "email": f"d{d}h{hh}@x.com"})

    got = lambda **p: {i["email"] for i in _get(client, h, event="logout", **p).json()["items"]}  # noqa: E731
    assert got(date_from="2026-09-10", date_to="2026-09-11") == {"d10h0@x.com", "d10h12@x.com", "d11h23@x.com"}
    assert got(date_from="2026-09-11") == {"d11h23@x.com", "d12h0@x.com"}
    assert got(date_to="2026-09-09") == {"d9h23@x.com"}
    assert _get(client, h, date_from="2026-09-12", date_to="2026-09-01").status_code == 400
    assert _get(client, h, date_from="not-a-date").status_code == 422


# ------------------------------------------------ the log records who did what


def test_admin_actions_store_the_actors_email(client, monkeypatch):
    import app.config.db as dbmod
    import app.routers.admin_users as admin_mod

    for name in ("users_col", "refresh_tokens_col"):
        monkeypatch.setattr(admin_mod, name, dbmod.db[name.replace("_col", "")])
    monkeypatch.setattr(admin_mod, "otp_verifications_col", dbmod.db["otp_verifications"])
    h = _admin_headers(client)
    officer = _seed("lmo", "pending@example.com")
    dbmod.users_col.update_one({"_id": officer["_id"]}, {"$set": {"status": "pending"}})

    assert client.post(f"/api/v1/admin/users/{officer['_id']}/approve", headers=h).status_code == 200
    assert client.post(f"/api/v1/admin/users/{officer['_id']}/reject", headers=h).status_code == 200

    rows = _get(client, h, search="pending@example.com").json()["items"]
    by_event = {r["event"]: r for r in rows}
    assert by_event["account_approved"]["actor_email"] == "boss@example.com"
    assert by_event["account_suspended"]["actor_email"] == "boss@example.com"
    # and it's findable from the admin's side too
    assert _get(client, h, search="boss@example.com", event="account_suspended").json()["total"] == 1


# --------------------------------------------------- the filter list can't drift


def _event_names_used_in_source() -> set[str]:
    used = set()
    paths = list((BACKEND_DIR / "app").rglob("*.py")) + list(BACKEND_DIR.glob("*.py"))
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", getattr(node.func, "attr", None))
                if name == "log_event" and node.args and isinstance(node.args[0], ast.Constant):
                    used.add(node.args[0].value)
    return used


def test_known_events_match_what_the_code_really_logs():
    used = _event_names_used_in_source()
    assert used, "found no log_event() calls - the scan is broken"
    assert used - set(KNOWN_AUDIT_EVENTS) == set(), "log_event() uses names missing from KNOWN_AUDIT_EVENTS"
    assert set(KNOWN_AUDIT_EVENTS) - used == set(), "KNOWN_AUDIT_EVENTS lists names nothing logs"
    assert len(set(KNOWN_AUDIT_EVENTS)) == len(KNOWN_AUDIT_EVENTS)


def test_every_outcome_the_code_uses_is_filterable():
    outcomes = set()
    paths = list((BACKEND_DIR / "app").rglob("*.py")) + list(BACKEND_DIR.glob("*.py"))
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "log_event":
                for kw in node.keywords:
                    if kw.arg == "outcome" and isinstance(kw.value, ast.Constant):
                        outcomes.add(kw.value.value)
    assert outcomes <= set(AUDIT_OUTCOMES), outcomes - set(AUDIT_OUTCOMES)
