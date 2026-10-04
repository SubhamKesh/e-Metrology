"""
Tests for:
  - login / logout / refresh audit events
  - change-password signing out every other session (but not the current one)
"""
import pytest
from passlib.context import CryptContext

from app.config.settings import LOGIN_MAX_ATTEMPTS

from mfa_helpers import enroll_mfa, full_login

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
OLD = "Old-Passw0rd!"
NEW = "Brand-New-Pass1!"


@pytest.fixture(autouse=True)
def no_real_email(client, monkeypatch):
    """change-password sends a notice in a background task — keep it local."""
    import app.services.mailer as mailer_mod

    sent = []
    monkeypatch.setattr(mailer_mod, "send_email", lambda to, subject, body, html=None, sender=None: sent.append(to) or True)
    return sent


def _seed(role="owner", email="u@example.com", password=OLD, **extra) -> dict:
    import app.config.db as dbmod

    doc = {"name": f"Test {role}", "email": email, "password": _pwd.hash(password), "role": role,
           "status": "active", "token_version": 0, **extra}
    doc["_id"] = dbmod.users_col.insert_one(doc).inserted_id
    creds = {"email": email, "password": password, "_id": doc["_id"]}
    if role in ("lmo", "gatc", "admin"):
        creds["mfa_secret"] = enroll_mfa(doc["_id"])
    return creds


def _login(client, creds, **extra):
    if "mfa_secret" in creds:
        return full_login(client, creds, **extra)
    client.cookies.clear()
    r = client.post("/api/v1/auth/login", json={"email": creds["email"], "password": creds["password"], **extra})
    assert r.status_code == 200, r.text
    return r


def _bearer(r):
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _audit(event=None):
    import app.config.db as dbmod

    return list(dbmod.db["audit_logs"].find({"event": event} if event else {}))


# ---------------------------------------------------------------- login audit


def test_successful_login_is_audited(client):
    creds = _seed()
    _login(client, creds)
    ev = _audit("login_success")[-1]
    assert ev["outcome"] == "success" and ev["email"] == creds["email"] and ev["role"] == "owner"
    assert ev["user_id"] == str(creds["_id"]) and ev["detail"] is None


def test_login_with_remember_me_is_marked(client):
    _login(client, _seed(), remember_me=True)
    assert _audit("login_success")[-1]["detail"] == "remember_me"


def test_officer_remember_me_request_is_not_marked(client):
    _login(client, _seed("lmo", "off@example.com"), remember_me=True)
    # Officers sign in with a second step; the audit trail records how.
    assert _audit("login_success")[-1]["detail"] == "mfa_totp"


def test_failed_logins_are_audited(client):
    creds = _seed()
    client.post("/api/v1/auth/login", json={"email": creds["email"], "password": "nope"})
    client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": "nope"})
    details = [(e["detail"], e["email"], e["user_id"] is not None) for e in _audit("login_failed")]
    assert details == [("wrong_password", creds["email"], True), ("unknown_email", "ghost@example.com", False)]


def test_lockout_is_audited(client):
    creds = _seed()
    for _ in range(LOGIN_MAX_ATTEMPTS):
        client.post("/api/v1/auth/login", json={"email": creds["email"], "password": "wrong"})
    r = client.post("/api/v1/auth/login", json={"email": creds["email"], "password": creds["password"]})
    assert r.status_code == 429

    failures = [e["detail"] for e in _audit("login_failed")]
    assert failures[:-1] == ["wrong_password"] * (LOGIN_MAX_ATTEMPTS - 1)
    assert failures[-1] == "wrong_password_account_locked"
    blocked = _audit("login_blocked")[-1]
    assert blocked["detail"] == "account_locked" and blocked["outcome"] == "blocked"


@pytest.mark.parametrize("status,detail,code", [("pending", "account_pending", 403), ("rejected", "account_rejected", 403)])
def test_blocked_account_status_is_audited(client, status, detail, code):
    creds = _seed("lmo", f"{status}@example.com", status=status)
    r = client.post("/api/v1/auth/login", json={"email": creds["email"], "password": creds["password"]})
    assert r.status_code == code
    assert _audit("login_blocked")[-1]["detail"] == detail


def test_audit_never_contains_passwords_or_tokens(client):
    creds = _seed()
    client.post("/api/v1/auth/login", json={"email": creds["email"], "password": "SuperSecret-Guess1!"})
    r = _login(client, creds)
    blob = str(_audit())
    assert "SuperSecret-Guess1!" not in blob and creds["password"] not in blob and r.json()["token"] not in blob


# ----------------------------------------------------------- logout / refresh


def test_logout_is_audited(client):
    creds = _seed()
    _login(client, creds)
    assert client.post("/api/v1/auth/logout").status_code == 204
    ev = _audit("logout")[-1]
    assert ev["email"] == creds["email"] and ev["user_id"] == str(creds["_id"])


def test_logout_without_a_session_writes_nothing(client):
    client.cookies.clear()
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert _audit("logout") == []


def test_logout_all_is_audited(client):
    creds = _seed()
    r = _login(client, creds)
    assert client.post("/api/v1/auth/logout-all", headers=_bearer(r)).status_code == 204
    assert _audit("logout_all")[-1]["email"] == creds["email"]


def test_reusing_a_revoked_refresh_token_is_audited(client):
    creds = _seed()
    login = _login(client, creds)
    stale = login.cookies
    client.cookies.clear()
    assert client.post("/api/v1/auth/refresh", cookies=stale).status_code == 200  # rotates
    client.cookies.clear()
    assert client.post("/api/v1/auth/refresh", cookies=stale).status_code == 401  # replay

    ev = _audit("refresh_rejected")[-1]
    assert ev["outcome"] == "blocked" and ev["detail"] == "revoked_token_presented"
    assert ev["user_id"] == str(creds["_id"])


def test_refresh_with_no_cookie_is_not_audited(client):
    client.cookies.clear()
    assert client.post("/api/v1/auth/refresh").status_code == 401
    assert _audit("refresh_rejected") == []


# -------------------------------------- change-password signs out other sessions


def test_change_password_signs_out_every_other_session_but_not_this_one(client):
    creds = _seed()
    device_a = _login(client, creds)   # the one changing the password
    device_b = _login(client, creds)   # some other browser / a thief

    client.cookies.clear()
    r = client.post(
        "/api/v1/auth/change-password",
        headers=_bearer(device_a),
        cookies=device_a.cookies,
        json={"current_password": OLD, "new_password": NEW},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # Other device: access token dead, refresh token dead.
    assert client.get("/api/v1/auth/me", headers=_bearer(device_b)).status_code == 401
    client.cookies.clear()
    assert client.post("/api/v1/auth/refresh", cookies=device_b.cookies).status_code == 401

    # This device's OLD tokens are dead too (they predate the change)...
    assert client.get("/api/v1/auth/me", headers=_bearer(device_a)).status_code == 401
    client.cookies.clear()
    assert client.post("/api/v1/auth/refresh", cookies=device_a.cookies).status_code == 401

    # ...but the replacement session issued in the response works.
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['token']}"}).status_code == 200
    client.cookies.clear()
    assert client.post("/api/v1/auth/refresh", cookies=r.cookies).status_code == 200

    assert body["must_change_password"] is False and body["email"] == creds["email"]
    assert client.post("/api/v1/auth/login", json={"email": creds["email"], "password": NEW}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": creds["email"], "password": OLD}).status_code == 401


def test_change_password_keeps_remember_me_on_the_new_session(client):
    creds = _seed()
    login = _login(client, creds, remember_me=True)
    client.cookies.clear()
    r = client.post(
        "/api/v1/auth/change-password", headers=_bearer(login), cookies=login.cookies,
        json={"current_password": OLD, "new_password": NEW},
    )
    assert r.json()["remember_me"] is True
    cookie = [h for h in r.headers.get_list("set-cookie") if h.startswith("refresh_token=")][0].lower()
    assert "max-age" in cookie


def test_change_password_on_a_plain_session_stays_a_session_cookie(client):
    creds = _seed()
    login = _login(client, creds)
    client.cookies.clear()
    r = client.post(
        "/api/v1/auth/change-password", headers=_bearer(login), cookies=login.cookies,
        json={"current_password": OLD, "new_password": NEW},
    )
    assert r.json()["remember_me"] is False
    cookie = [h for h in r.headers.get_list("set-cookie") if h.startswith("refresh_token=")][0].lower()
    assert "max-age" not in cookie


def test_change_password_without_a_refresh_cookie_still_works(client):
    """e.g. a browser that blocks cross-site cookies: only the access token arrives."""
    creds = _seed()
    login = _login(client, creds)
    client.cookies.clear()
    r = client.post(
        "/api/v1/auth/change-password", headers=_bearer(login),
        json={"current_password": OLD, "new_password": NEW},
    )
    assert r.status_code == 200 and r.json()["remember_me"] is False
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {r.json()['token']}"}).status_code == 200


def test_forced_first_login_change_gives_the_officer_a_working_session(client):
    creds = _seed("lmo", "newofficer@example.com", must_change_password=True)
    login = _login(client, creds)
    assert login.json()["user"]["must_change_password"] is True
    client.cookies.clear()
    r = client.post(
        "/api/v1/auth/change-password", headers=_bearer(login), cookies=login.cookies,
        json={"current_password": OLD, "new_password": NEW},
    )
    assert r.status_code == 200 and r.json()["must_change_password"] is False
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {r.json()['token']}"})
    assert me.status_code == 200 and me.json()["must_change_password"] is False
    assert r.json()["remember_me"] is False  # officers never get remember-me


def test_failed_change_password_leaves_other_sessions_alone(client):
    creds = _seed()
    device_a = _login(client, creds)
    device_b = _login(client, creds)
    client.cookies.clear()
    bad = client.post(
        "/api/v1/auth/change-password", headers=_bearer(device_a),
        json={"current_password": "wrong", "new_password": NEW},
    )
    assert bad.status_code == 401
    assert client.get("/api/v1/auth/me", headers=_bearer(device_b)).status_code == 200
    assert client.get("/api/v1/auth/me", headers=_bearer(device_a)).status_code == 200


def test_change_password_audit_notes_sessions_were_revoked(client):
    creds = _seed()
    login = _login(client, creds)
    client.cookies.clear()
    client.post("/api/v1/auth/change-password", headers=_bearer(login),
                json={"current_password": OLD, "new_password": NEW})
    assert _audit("password_changed")[-1]["detail"] == "other_sessions_revoked"
