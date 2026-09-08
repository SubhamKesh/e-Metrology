"""
Tests for the auth hardening added on top of the original login/register:
refresh-token rotation, revocation-on-reuse, account lockout with
exponential backoff, and logout-all via token_version.
"""


def test_login_issues_access_token_and_refresh_cookie(client, registered_owner):
    r = client.post("/api/v1/auth/login", json=registered_owner)
    assert r.status_code == 200
    assert r.json()["token"]
    assert "refresh_token" in r.cookies


def test_wrong_password_does_not_leak_which_field_was_wrong(client, registered_owner):
    r = client.post(
        "/api/v1/auth/login",
        json={"email": registered_owner["email"], "password": "nope"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid email or password"

    r2 = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "nope"},
    )
    assert r2.status_code == 401
    assert r2.json()["detail"] == "Invalid email or password"


def test_account_locks_out_after_max_failed_attempts(client, registered_owner):
    from app.config.settings import LOGIN_MAX_ATTEMPTS

    for _ in range(LOGIN_MAX_ATTEMPTS):
        r = client.post(
            "/api/v1/auth/login",
            json={"email": registered_owner["email"], "password": "wrong"},
        )
        assert r.status_code == 401

    # One more attempt (even with the CORRECT password) should now be
    # rejected as locked, not re-checked against the password.
    r = client.post("/api/v1/auth/login", json=registered_owner)
    assert r.status_code == 429


def test_refresh_token_rotates_and_rejects_reuse(client, registered_owner):
    login = client.post("/api/v1/auth/login", json=registered_owner)
    cookies = login.cookies

    first_refresh = client.post("/api/v1/auth/refresh", cookies=cookies)
    assert first_refresh.status_code == 200
    # The access token itself can legitimately be byte-identical if issued
    # within the same second (same sub/tv/exp claims) — what must actually
    # change on rotation is the refresh token cookie.
    assert first_refresh.cookies.get("refresh_token") != cookies.get("refresh_token")

    # Reusing the now-rotated-away original refresh token must fail —
    # this is what makes a stolen-but-unused refresh token a dead end.
    reuse = client.post("/api/v1/auth/refresh", cookies=cookies)
    assert reuse.status_code == 401


def test_logout_all_revokes_existing_access_token(client, registered_owner):
    login = client.post("/api/v1/auth/login", json=registered_owner)
    access_token = login.json()["token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    logout_all = client.post("/api/v1/auth/logout-all", headers=headers)
    assert logout_all.status_code == 204

    # The access token was valid (not expired) but its token_version is now
    # stale, so it must be rejected.
    r = client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 401
    assert r.json()["detail"] == "Token has been revoked"


def test_security_headers_present_on_every_response(client):
    r = client.get("/api/v1/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"


def test_oversized_request_body_is_rejected(client):
    from app.config.settings import MAX_REQUEST_BODY_BYTES

    oversized_password = "x" * (MAX_REQUEST_BODY_BYTES + 1)
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "a@a.com", "password": oversized_password},
    )
    assert r.status_code == 413
