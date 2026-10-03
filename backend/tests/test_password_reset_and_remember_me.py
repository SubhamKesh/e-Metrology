"""
Tests for "Remember me" (persistent vs session refresh cookie, carried
through rotation) and for forgot-password / reset-password (OTP-based).
"""
import re
from datetime import datetime, timedelta, timezone

import pytest

from app.config.settings import (
    LOGIN_MAX_ATTEMPTS,
    REFRESH_TOKEN_EXPIRES_DAYS,
    REMEMBER_ME_REFRESH_TOKEN_EXPIRES_DAYS,
)

NEW_PASSWORD = "Brand-New-Pass1!"


@pytest.fixture
def sent_emails(client, monkeypatch):
    """Points the OTP collection at the same in-memory DB the `client`
    fixture uses, and captures outgoing emails instead of sending them."""
    import app.config.db as dbmod
    import app.routers.auth as auth_mod
    import app.services.otp as otp_mod

    monkeypatch.setattr(otp_mod, "otp_verifications_col", dbmod.db["otp_verifications"])

    outbox: list[dict] = []

    def fake_send_email(to, subject, body, html=None):
        outbox.append({"to": to, "subject": subject, "body": body})
        return True

    monkeypatch.setattr(auth_mod, "send_email", fake_send_email)
    return outbox


def _code_from(email: dict) -> str:
    match = re.search(r"\b(\d{6})\b", email["body"])
    assert match, f"no 6-digit code in: {email['body']!r}"
    return match.group(1)


def _request_code(client, sent_emails, email="owner@example.com") -> str:
    r = client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert r.status_code == 200
    assert sent_emails, "expected a reset email to be sent"
    return _code_from(sent_emails[-1])


def _refresh_cookie_header(response) -> str:
    headers = [h for h in response.headers.get_list("set-cookie") if h.startswith("refresh_token=")]
    assert len(headers) == 1
    return headers[0]


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- remember me


def test_login_without_remember_me_sets_session_cookie(client, registered_owner):
    import app.config.db as dbmod

    r = client.post("/api/v1/auth/login", json=registered_owner)
    assert r.status_code == 200

    cookie = _refresh_cookie_header(r).lower()
    assert "max-age" not in cookie and "expires=" not in cookie  # session cookie

    stored = dbmod.refresh_tokens_col.find_one({})
    assert stored["remember_me"] is False
    expected = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRES_DAYS)
    assert abs(_as_utc(stored["expires_at"]) - expected) < timedelta(minutes=1)


def test_login_with_remember_me_sets_persistent_cookie(client, registered_owner):
    import app.config.db as dbmod

    r = client.post("/api/v1/auth/login", json={**registered_owner, "remember_me": True})
    assert r.status_code == 200

    cookie = _refresh_cookie_header(r).lower()
    assert f"max-age={REMEMBER_ME_REFRESH_TOKEN_EXPIRES_DAYS * 86400}" in cookie

    stored = dbmod.refresh_tokens_col.find_one({})
    assert stored["remember_me"] is True
    expected = datetime.now(timezone.utc) + timedelta(days=REMEMBER_ME_REFRESH_TOKEN_EXPIRES_DAYS)
    assert abs(_as_utc(stored["expires_at"]) - expected) < timedelta(minutes=1)


def test_refresh_keeps_remember_me_choice(client, registered_owner):
    login = client.post("/api/v1/auth/login", json={**registered_owner, "remember_me": True})
    refreshed = client.post("/api/v1/auth/refresh", cookies=login.cookies)
    assert refreshed.status_code == 200
    assert "max-age" in _refresh_cookie_header(refreshed).lower()


def test_refresh_keeps_session_cookie_when_not_remembered(client, registered_owner):
    login = client.post("/api/v1/auth/login", json=registered_owner)
    refreshed = client.post("/api/v1/auth/refresh", cookies=login.cookies)
    assert refreshed.status_code == 200
    assert "max-age" not in _refresh_cookie_header(refreshed).lower()


def test_remember_me_must_be_a_boolean_field_not_required(client, registered_owner):
    # Omitting it entirely is the pre-existing contract and must still work.
    assert client.post("/api/v1/auth/login", json=registered_owner).status_code == 200


# ------------------------------------------------------------ forgot password


def test_forgot_password_sends_code_for_existing_account(client, registered_owner, sent_emails):
    r = client.post("/api/v1/auth/forgot-password", json={"email": registered_owner["email"]})
    assert r.status_code == 200
    assert r.json() == {"sent": True}
    assert len(sent_emails) == 1
    assert sent_emails[0]["to"] == registered_owner["email"]
    assert re.search(r"\b\d{6}\b", sent_emails[0]["body"])


def test_forgot_password_is_case_insensitive_on_email(client, registered_owner, sent_emails):
    r = client.post("/api/v1/auth/forgot-password", json={"email": "  OWNER@Example.com "})
    assert r.status_code == 200
    assert len(sent_emails) == 1


def test_forgot_password_does_not_reveal_whether_account_exists(client, registered_owner, sent_emails):
    known = client.post("/api/v1/auth/forgot-password", json={"email": registered_owner["email"]})
    unknown = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"})

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json() == {"sent": True}
    # ...and nothing was emailed for the address with no account.
    assert [m["to"] for m in sent_emails] == [registered_owner["email"]]


def test_forgot_password_cooldown_blocks_a_second_email(client, registered_owner, sent_emails):
    first = client.post("/api/v1/auth/forgot-password", json={"email": registered_owner["email"]})
    second = client.post("/api/v1/auth/forgot-password", json={"email": registered_owner["email"]})
    assert first.json() == second.json() == {"sent": True}  # same answer either way
    assert len(sent_emails) == 1


def test_forgot_password_rejects_malformed_email(client, sent_emails):
    r = client.post("/api/v1/auth/forgot-password", json={"email": "not-an-email"})
    assert r.status_code == 422
    assert not sent_emails


# ------------------------------------------------------------- reset password


def test_reset_password_happy_path(client, registered_owner, sent_emails):
    code = _request_code(client, sent_emails)

    r = client.post(
        "/api/v1/auth/reset-password",
        json={"email": registered_owner["email"], "code": code, "new_password": NEW_PASSWORD},
    )
    assert r.status_code == 200
    assert r.json() == {"reset": True}

    old = client.post("/api/v1/auth/login", json=registered_owner)
    assert old.status_code == 401
    new = client.post(
        "/api/v1/auth/login", json={"email": registered_owner["email"], "password": NEW_PASSWORD}
    )
    assert new.status_code == 200


def test_reset_code_is_single_use(client, registered_owner, sent_emails):
    code = _request_code(client, sent_emails)
    body = {"email": registered_owner["email"], "code": code, "new_password": NEW_PASSWORD}

    assert client.post("/api/v1/auth/reset-password", json=body).status_code == 200
    again = client.post("/api/v1/auth/reset-password", json={**body, "new_password": "Another-Pass2@"})
    assert again.status_code == 400

    # The second attempt must not have changed the password.
    ok = client.post(
        "/api/v1/auth/login", json={"email": registered_owner["email"], "password": NEW_PASSWORD}
    )
    assert ok.status_code == 200


def test_reset_revokes_existing_sessions(client, registered_owner, sent_emails):
    login = client.post("/api/v1/auth/login", json={**registered_owner, "remember_me": True})
    headers = {"Authorization": f"Bearer {login.json()['token']}"}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    code = _request_code(client, sent_emails)
    client.post(
        "/api/v1/auth/reset-password",
        json={"email": registered_owner["email"], "code": code, "new_password": NEW_PASSWORD},
    )

    # Old access token: dead (token_version bumped).
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    # Old refresh token: dead (revoked) — even though the cookie is "remembered".
    assert client.post("/api/v1/auth/refresh", cookies=login.cookies).status_code == 401


def test_reset_clears_failed_login_lockout(client, registered_owner, sent_emails):
    for _ in range(LOGIN_MAX_ATTEMPTS):
        client.post("/api/v1/auth/login", json={"email": registered_owner["email"], "password": "wrong"})
    locked = client.post("/api/v1/auth/login", json=registered_owner)
    assert locked.status_code == 429

    code = _request_code(client, sent_emails)
    client.post(
        "/api/v1/auth/reset-password",
        json={"email": registered_owner["email"], "code": code, "new_password": NEW_PASSWORD},
    )

    r = client.post(
        "/api/v1/auth/login", json={"email": registered_owner["email"], "password": NEW_PASSWORD}
    )
    assert r.status_code == 200


def test_wrong_code_is_rejected_with_generic_message(client, registered_owner, sent_emails):
    code = _request_code(client, sent_emails)
    wrong = "000000" if code != "000000" else "111111"

    r = client.post(
        "/api/v1/auth/reset-password",
        json={"email": registered_owner["email"], "code": wrong, "new_password": NEW_PASSWORD},
    )
    assert r.status_code == 400
    generic = r.json()["detail"]

    # Same message for an email that has no account at all.
    r2 = client.post(
        "/api/v1/auth/reset-password",
        json={"email": "nobody@example.com", "code": wrong, "new_password": NEW_PASSWORD},
    )
    assert r2.status_code == 400
    assert r2.json()["detail"] == generic

    # Password untouched.
    assert client.post("/api/v1/auth/login", json=registered_owner).status_code == 200


def test_code_is_burned_after_max_wrong_attempts(client, registered_owner, sent_emails):
    from app.services.otp import MAX_ATTEMPTS

    code = _request_code(client, sent_emails)
    wrong = "000000" if code != "000000" else "111111"
    body = {"email": registered_owner["email"], "new_password": NEW_PASSWORD}

    for _ in range(MAX_ATTEMPTS):
        assert client.post("/api/v1/auth/reset-password", json={**body, "code": wrong}).status_code == 400

    # Even the CORRECT code no longer works — the attacker's guesses used it up.
    assert client.post("/api/v1/auth/reset-password", json={**body, "code": code}).status_code == 400
    assert client.post("/api/v1/auth/login", json=registered_owner).status_code == 200


def test_expired_code_is_rejected(client, registered_owner, sent_emails):
    import app.config.db as dbmod

    code = _request_code(client, sent_emails)
    dbmod.db["otp_verifications"].update_one(
        {"identifier": registered_owner["email"], "purpose": "password_reset"},
        {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)}},
    )

    r = client.post(
        "/api/v1/auth/reset-password",
        json={"email": registered_owner["email"], "code": code, "new_password": NEW_PASSWORD},
    )
    assert r.status_code == 400


def test_too_short_password_is_rejected_without_burning_the_code(client, registered_owner, sent_emails):
    code = _request_code(client, sent_emails)

    bad = client.post(
        "/api/v1/auth/reset-password",
        json={"email": registered_owner["email"], "code": code, "new_password": "abc"},
    )
    assert bad.status_code == 422

    good = client.post(
        "/api/v1/auth/reset-password",
        json={"email": registered_owner["email"], "code": code, "new_password": NEW_PASSWORD},
    )
    assert good.status_code == 200


def test_malformed_code_is_rejected(client, registered_owner, sent_emails):
    r = client.post(
        "/api/v1/auth/reset-password",
        json={"email": registered_owner["email"], "code": "12ab", "new_password": NEW_PASSWORD},
    )
    assert r.status_code == 422


def test_signup_verification_cannot_be_used_to_reset_a_password(client, registered_owner, sent_emails):
    """A verified 'email_verify' proof (signup flow) must not unlock a reset,
    even though verify_otp()'s already-verified branch ignores the code."""
    import app.config.db as dbmod

    dbmod.db["otp_verifications"].insert_one(
        {
            "identifier": registered_owner["email"],
            "purpose": "email_verify",
            "code_hash": "irrelevant",
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
            "attempts": 0,
            "verified": True,
        }
    )
    r = client.post(
        "/api/v1/auth/reset-password",
        json={"email": registered_owner["email"], "code": "123456", "new_password": NEW_PASSWORD},
    )
    assert r.status_code == 400
    assert client.post("/api/v1/auth/login", json=registered_owner).status_code == 200


def test_reset_clears_must_change_password_flag(client, registered_owner, sent_emails):
    import app.config.db as dbmod

    dbmod.users_col.update_one({"email": registered_owner["email"]}, {"$set": {"must_change_password": True}})
    code = _request_code(client, sent_emails)
    client.post(
        "/api/v1/auth/reset-password",
        json={"email": registered_owner["email"], "code": code, "new_password": NEW_PASSWORD},
    )
    user = dbmod.users_col.find_one({"email": registered_owner["email"]})
    assert user["must_change_password"] is False
