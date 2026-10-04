"""
Tests for the government-readiness additions:
  1. password policy (8-64 chars, upper/lower/digit/special, not common)
  2. officers/admin cannot self-service reset; admin-initiated reset works
  3. "Remember me" never applies to officer/admin accounts
  4. "password was changed" emails
  5. audit log entries
"""
import re

import pytest
from passlib.context import CryptContext

from app.utils.validators import validate_password

from mfa_helpers import enroll_mfa, full_login

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
GOOD = "Str0ng!Passw0rd"


# ------------------------------------------------------------------ fixtures


@pytest.fixture
def outbox(client, monkeypatch):
    """Captures every email (reset codes, change notices, admin reset) and
    wires the OTP collection to the in-memory DB."""
    import app.config.db as dbmod
    import app.routers.admin_users as admin_mod
    import app.routers.auth as auth_mod
    import app.services.otp as otp_mod

    monkeypatch.setattr(otp_mod, "otp_verifications_col", dbmod.db["otp_verifications"])
    # The admin router imported these collections by name, so patch them too.
    monkeypatch.setattr(admin_mod, "otp_verifications_col", dbmod.db["otp_verifications"])
    monkeypatch.setattr(admin_mod, "users_col", dbmod.db["users"])
    monkeypatch.setattr(admin_mod, "refresh_tokens_col", dbmod.db["refresh_tokens"])
    box: list[dict] = []

    def fake_send_email(to, subject, body, html=None, sender=None):
        box.append({"to": to, "subject": subject, "body": body})
        return True

    # Notices go through mailer.send_email; patch it at every import site.
    import app.services.mailer as mailer_mod

    monkeypatch.setattr(mailer_mod, "send_email", fake_send_email)
    monkeypatch.setattr(auth_mod, "send_email", fake_send_email)
    # Admin reset: pretend SMTP is configured, no queue -> inline send.
    monkeypatch.setattr(admin_mod, "smtp_is_configured", lambda: True)
    monkeypatch.setattr(admin_mod, "get_queue", lambda: None)
    return box


def _seed(role: str, email: str, password: str = "Old-Passw0rd!", **extra) -> dict:
    import app.config.db as dbmod

    doc = {
        "name": f"Test {role}",
        "email": email,
        "password": _pwd.hash(password),
        "role": role,
        "status": "active",
        "token_version": 0,
        **extra,
    }
    doc["_id"] = dbmod.users_col.insert_one(doc).inserted_id
    creds = {"email": email, "password": password, "_id": doc["_id"]}
    if role in ("lmo", "gatc", "admin"):
        # Officer/admin accounts must have two-step verification set up to sign in.
        creds["mfa_secret"] = enroll_mfa(doc["_id"])
    return creds


def _auth(client, creds) -> dict:
    if "mfa_secret" in creds:
        r = full_login(client, creds)
    else:
        r = client.post("/api/v1/auth/login", json={"email": creds["email"], "password": creds["password"]})
        assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _audit(event=None):
    import app.config.db as dbmod

    q = {"event": event} if event else {}
    return list(dbmod.db["audit_logs"].find(q))


def _code(outbox) -> str:
    mails = [m for m in outbox if "reset code" in m["subject"]]
    assert mails, "no reset-code email was sent"
    return re.search(r"\b(\d{6})\b", mails[-1]["body"]).group(1)


# ------------------------------------------------------- 1. password policy


@pytest.mark.parametrize(
    "bad",
    [
        "Ab1!xyz",            # 7 chars
        "alllowercase1!",     # no uppercase
        "ALLUPPERCASE1!",     # no lowercase
        "NoDigitsHere!!",     # no digit
        "NoSpecial12345",     # no special char
        "Password@123",       # complex-looking but on the common list
        "A1!" + "a" * 70,     # too long
    ],
)
def test_weak_passwords_are_rejected(bad):
    with pytest.raises(ValueError):
        validate_password(bad)


@pytest.mark.parametrize("good", [GOOD, "Abcdef1!", "correct Horse 9 battery", "Ünïcode-Pass1"])
def test_strong_passwords_are_accepted(good):
    assert validate_password(good) == good


def test_policy_message_lists_what_is_missing():
    with pytest.raises(ValueError) as exc:
        validate_password("abcdefghi")
    msg = str(exc.value)
    assert "uppercase" in msg and "number" in msg and "special" in msg and "lowercase" not in msg


def test_register_enforces_policy(client):
    r = client.post(
        "/api/v1/auth/register",
        json={"name": "A B", "email": "new@example.com", "password": "weakpass", "role": "owner",
              "org_name": "X", "contact": "9876543210"},
    )
    assert r.status_code == 422


def test_change_password_enforces_policy_and_difference(client, registered_owner, outbox):
    headers = _auth(client, registered_owner)
    url = "/api/v1/auth/change-password"

    weak = client.post(url, headers=headers, json={"current_password": registered_owner["password"], "new_password": "weakpass"})
    assert weak.status_code == 422

    same = client.post(url, headers=headers, json={"current_password": GOOD, "new_password": GOOD})
    assert same.status_code == 401  # current password wrong -> checked first

    wrong = client.post(url, headers=headers, json={"current_password": "nope", "new_password": GOOD})
    assert wrong.status_code == 401


def test_change_password_rejects_reusing_current_password(client, outbox):
    creds = _seed("owner", "pw@example.com", password=GOOD)
    headers = _auth(client, creds)
    r = client.post("/api/v1/auth/change-password", headers=headers, json={"current_password": GOOD, "new_password": GOOD})
    assert r.status_code == 400
    assert "different" in r.json()["detail"]


def test_old_weak_password_can_still_log_in(client, registered_owner):
    # registered_owner's "correct-password" would fail the new policy — login must not enforce it.
    assert client.post("/api/v1/auth/login", json=registered_owner).status_code == 200


# --------------------------------- 2. officers/admin cannot self-reset

@pytest.mark.parametrize("role", ["lmo", "gatc", "admin"])
def test_privileged_roles_get_no_reset_email(client, outbox, role):
    creds = _seed(role, f"{role}@example.com")
    r = client.post("/api/v1/auth/forgot-password", json={"email": creds["email"]})
    assert r.status_code == 200 and r.json() == {"sent": True}  # same answer as for any email
    assert outbox == []
    ev = _audit("password_reset_requested")[-1]
    assert ev["outcome"] == "blocked" and ev["role"] == role


@pytest.mark.parametrize("role", ["lmo", "gatc", "admin"])
def test_privileged_role_cannot_reset_even_with_a_valid_code(client, outbox, role):
    """Defence in depth: forge a valid OTP for an officer and try to use it."""
    import app.config.db as dbmod
    from app.services.otp import generate_and_store_otp
    import app.services.otp as otp_mod

    creds = _seed(role, f"{role}2@example.com")
    code = generate_and_store_otp(identifier=creds["email"], purpose="password_reset")
    assert otp_mod.otp_verifications_col is dbmod.db["otp_verifications"]

    r = client.post(
        "/api/v1/auth/reset-password",
        json={"email": creds["email"], "code": code, "new_password": GOOD},
    )
    assert r.status_code == 400
    assert client.post("/api/v1/auth/login", json={"email": creds["email"], "password": creds["password"]}).status_code == 200
    assert _audit("password_reset_failed")[-1]["outcome"] == "blocked"


def test_admin_can_reset_officer_password(client, outbox):
    admin = _seed("admin", "boss@example.com")
    officer = _seed("lmo", "officer@example.com", failed_login_attempts=5)
    off_headers = {"Authorization": f"Bearer {full_login(client, officer).json()['token']}"}

    r = client.post(f"/api/v1/admin/users/{officer['_id']}/reset-password", headers=_auth(client, admin))
    assert r.status_code == 200, r.text
    body = r.json()
    temp = body["temp_password"]
    assert body["user"]["must_change_password"] is True and body["emailed"] is True
    assert outbox and outbox[-1]["to"] == officer["email"] and temp in outbox[-1]["body"]

    # old password dead, old session dead, temp password works and forces change
    assert client.post("/api/v1/auth/login", json={"email": officer["email"], "password": officer["password"]}).status_code == 401
    assert client.get("/api/v1/auth/me", headers=off_headers).status_code == 401
    # The temp password gets the officer through step one; their authenticator
    # (untouched by a password reset) still gates step two.
    step1 = client.post("/api/v1/auth/login", json={"email": officer["email"], "password": temp})
    assert step1.status_code == 200 and step1.json()["mfa_required"] is True and step1.json()["token"] is None
    new_login = full_login(client, {**officer, "password": temp})
    assert new_login.json()["user"]["must_change_password"] is True

    ev = _audit("admin_password_reset")[-1]
    assert ev["email"] == officer["email"] and ev["actor_id"] == str(admin["_id"])
    assert temp not in str(ev)  # secrets never reach the audit log


def test_admin_reset_clears_lockout_and_pending_codes(client, outbox):
    import app.config.db as dbmod

    admin = _seed("admin", "boss2@example.com")
    officer = _seed("gatc", "gatc9@example.com")
    dbmod.db["otp_verifications"].insert_one({"identifier": officer["email"], "purpose": "password_reset", "code_hash": "x"})
    for _ in range(10):
        client.post("/api/v1/auth/login", json={"email": officer["email"], "password": "wrong"})
    assert client.post("/api/v1/auth/login", json={"email": officer["email"], "password": officer["password"]}).status_code == 429

    temp = client.post(f"/api/v1/admin/users/{officer['_id']}/reset-password", headers=_auth(client, admin)).json()["temp_password"]
    assert client.post("/api/v1/auth/login", json={"email": officer["email"], "password": temp}).status_code == 200
    assert dbmod.db["otp_verifications"].count_documents({"identifier": officer["email"]}) == 0


def test_admin_reset_only_for_officers_and_only_by_admin(client, outbox):
    admin = _seed("admin", "boss3@example.com")
    owner = _seed("owner", "biz@example.com")
    other_admin = _seed("admin", "boss4@example.com")
    officer = _seed("lmo", "officer3@example.com")

    h = _auth(client, admin)
    assert client.post(f"/api/v1/admin/users/{owner['_id']}/reset-password", headers=h).status_code == 400
    assert client.post(f"/api/v1/admin/users/{other_admin['_id']}/reset-password", headers=h).status_code == 400
    assert client.post("/api/v1/admin/users/not-an-id/reset-password", headers=h).status_code == 400
    assert client.post("/api/v1/admin/users/64b000000000000000000000/reset-password", headers=h).status_code == 404

    # an officer / owner / anonymous caller is refused
    assert client.post(f"/api/v1/admin/users/{officer['_id']}/reset-password", headers=_auth(client, officer)).status_code == 403
    assert client.post(f"/api/v1/admin/users/{officer['_id']}/reset-password", headers=_auth(client, owner)).status_code == 403
    assert client.post(f"/api/v1/admin/users/{officer['_id']}/reset-password").status_code in (401, 403)


def test_forced_change_after_admin_reset_requires_a_new_strong_password(client, outbox):
    admin = _seed("admin", "boss5@example.com")
    officer = _seed("lmo", "officer5@example.com")
    temp = client.post(f"/api/v1/admin/users/{officer['_id']}/reset-password", headers=_auth(client, admin)).json()["temp_password"]
    h = _auth(client, {**officer, "password": temp})

    assert client.post("/api/v1/auth/change-password", headers=h, json={"current_password": temp, "new_password": "weak"}).status_code == 422
    ok = client.post("/api/v1/auth/change-password", headers=h, json={"current_password": temp, "new_password": GOOD})
    assert ok.status_code == 200 and ok.json()["must_change_password"] is False


# --------------------------------------- 3. remember me is owner-only


@pytest.mark.parametrize("role", ["lmo", "gatc", "admin"])
def test_remember_me_is_ignored_for_officers_and_admin(client, role):
    import app.config.db as dbmod

    creds = _seed(role, f"{role}@rm.example.com")
    r = full_login(client, creds, remember_me=True)
    assert r.status_code == 200
    assert r.json()["remember_me"] is False
    cookie = [h for h in r.headers.get_list("set-cookie") if h.startswith("refresh_token=")][0].lower()
    assert "max-age" not in cookie
    assert dbmod.refresh_tokens_col.find_one({"user_id": str(creds["_id"])})["remember_me"] is False


def test_remember_me_is_reported_back_for_owners(client, registered_owner):
    r = client.post("/api/v1/auth/login", json={**registered_owner, "remember_me": True})
    assert r.json()["remember_me"] is True
    r2 = client.post("/api/v1/auth/login", json=registered_owner)
    assert r2.json()["remember_me"] is False


def test_refresh_reports_remember_me(client, registered_owner):
    login = client.post("/api/v1/auth/login", json={**registered_owner, "remember_me": True})
    refreshed = client.post("/api/v1/auth/refresh", cookies=login.cookies)
    assert refreshed.json()["remember_me"] is True


# ------------------------------------------- 4. "password changed" email


def test_reset_sends_password_changed_email(client, registered_owner, outbox):
    client.post("/api/v1/auth/forgot-password", json={"email": registered_owner["email"]})
    code = _code(outbox)
    r = client.post("/api/v1/auth/reset-password", json={"email": registered_owner["email"], "code": code, "new_password": GOOD})
    assert r.status_code == 200
    notice = [m for m in outbox if "was changed" in m["subject"]]
    assert len(notice) == 1 and notice[0]["to"] == registered_owner["email"]
    assert GOOD not in notice[0]["body"] and "IST" in notice[0]["body"]


def test_change_password_sends_password_changed_email(client, outbox):
    creds = _seed("owner", "chg@example.com", password="Old-Passw0rd!")
    h = _auth(client, creds)
    r = client.post("/api/v1/auth/change-password", headers=h, json={"current_password": creds["password"], "new_password": GOOD})
    assert r.status_code == 200
    notice = [m for m in outbox if "was changed" in m["subject"]]
    assert len(notice) == 1 and notice[0]["to"] == creds["email"]


def test_failed_change_sends_no_email(client, outbox):
    creds = _seed("owner", "chg2@example.com")
    h = _auth(client, creds)
    client.post("/api/v1/auth/change-password", headers=h, json={"current_password": "wrong", "new_password": GOOD})
    assert [m for m in outbox if "was changed" in m["subject"]] == []


# ------------------------------------------------------------ 5. audit log


def test_full_reset_flow_is_audited_without_secrets(client, registered_owner, outbox):
    client.post("/api/v1/auth/forgot-password", json={"email": registered_owner["email"]}, headers={"x-forwarded-for": "203.0.113.7, 10.0.0.1"})
    code = _code(outbox)
    client.post("/api/v1/auth/reset-password", json={"email": registered_owner["email"], "code": "000000" if code != "000000" else "111111", "new_password": GOOD})
    client.post("/api/v1/auth/reset-password", json={"email": registered_owner["email"], "code": code, "new_password": GOOD})

    events = [(e["event"], e["outcome"]) for e in _audit()]
    assert ("password_reset_requested", "success") in events
    assert ("password_reset_failed", "failure") in events
    assert ("password_reset_completed", "success") in events

    requested = _audit("password_reset_requested")[0]
    assert requested["ip"] == "203.0.113.7" and requested["email"] == registered_owner["email"]
    blob = str(_audit())
    assert code not in blob and GOOD not in blob and "Brand" not in blob


def test_unknown_email_and_cooldown_are_audited(client, registered_owner, outbox):
    client.post("/api/v1/auth/forgot-password", json={"email": "ghost@example.com"})
    client.post("/api/v1/auth/forgot-password", json={"email": registered_owner["email"]})
    client.post("/api/v1/auth/forgot-password", json={"email": registered_owner["email"]})
    details = [e["detail"] for e in _audit("password_reset_requested")]
    assert details == ["no_account", "code_sent", "cooldown"]


def test_password_change_events_are_audited(client, outbox):
    creds = _seed("owner", "aud@example.com")
    h = _auth(client, creds)
    client.post("/api/v1/auth/change-password", headers=h, json={"current_password": "bad", "new_password": GOOD})
    client.post("/api/v1/auth/change-password", headers=h, json={"current_password": creds["password"], "new_password": GOOD})
    assert [e["outcome"] for e in _audit("password_change_failed")] == ["failure"]
    assert [e["outcome"] for e in _audit("password_changed")] == ["success"]


def test_audit_failure_never_breaks_the_request(client, registered_owner, outbox, monkeypatch):
    import app.services.audit as audit_mod

    class Broken:
        def insert_one(self, *_a, **_k):
            raise RuntimeError("mongo down")

    monkeypatch.setattr(audit_mod, "audit_logs_col", Broken())
    r = client.post("/api/v1/auth/forgot-password", json={"email": registered_owner["email"]})
    assert r.status_code == 200 and r.json() == {"sent": True}
