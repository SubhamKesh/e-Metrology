"""
Two-step verification (TOTP) for officer/admin accounts, plus the admin-side
controls and the audit events for account lifecycle (registration, officer
creation, approve, suspend).
"""
import base64
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from passlib.context import CryptContext

from app.config.settings import JWT_ALGORITHM, JWT_SECRET, LOGIN_MAX_ATTEMPTS
from app.utils.mfa import decrypt_secret, encrypt_secret, generate_recovery_codes, hash_recovery_code, qr_data_uri
from app.utils.totp import (
    TOTP_PERIOD,
    _code_for_step,
    current_step,
    generate_secret,
    provisioning_uri,
    totp_at,
    verify_totp,
)
from mfa_helpers import enroll_mfa, fresh_code, full_login

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
PASSWORD = "Old-Passw0rd!"
NEW_PASSWORD = "Brand-New-Pass1!"


@pytest.fixture(autouse=True)
def no_real_email(client, monkeypatch):
    import app.services.mailer as mailer_mod

    monkeypatch.setattr(mailer_mod, "send_email", lambda to, subject, body, html=None, sender=None: True)


def _seed(role="lmo", email="officer@example.com", mfa=False, **extra) -> dict:
    import app.config.db as dbmod

    doc = {"name": f"Test {role}", "email": email, "password": _pwd.hash(PASSWORD), "role": role,
           "status": "active", "token_version": 0, **extra}
    doc["_id"] = dbmod.users_col.insert_one(doc).inserted_id
    creds = {"email": email, "password": PASSWORD, "_id": doc["_id"]}
    if mfa:
        creds["mfa_secret"] = enroll_mfa(doc["_id"])
    return creds


def _step1(client, creds, expect=200):
    client.cookies.clear()
    r = client.post("/api/v1/auth/login", json={"email": creds["email"], "password": creds["password"]})
    assert r.status_code == expect, r.text
    return r.json()


def _bearer(r):
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _user(creds):
    import app.config.db as dbmod

    return dbmod.users_col.find_one({"_id": creds["_id"]})


def _audit(event=None):
    import app.config.db as dbmod

    return list(dbmod.db["audit_logs"].find({"event": event} if event else {}))


def _wrong(code):
    return "000000" if code != "000000" else "111111"


# =========================================================== TOTP primitives


def test_totp_matches_rfc6238_vectors():
    secret = base64.b32encode(b"12345678901234567890").decode()
    vectors = {59: "287082", 1111111109: "081804", 1111111111: "050471", 1234567890: "005924",
               2000000000: "279037", 20000000000: "353130"}
    for t, expected in vectors.items():
        assert totp_at(secret, t) == expected


def test_totp_window_replay_and_format_rules():
    secret = generate_secret()
    now = 1_700_000_000.0
    step = current_step(now)
    code = _code_for_step(secret, step)

    assert verify_totp(secret, code, for_time=now) == step
    assert verify_totp(secret, _code_for_step(secret, step - 1), for_time=now) == step - 1   # clock drift
    assert verify_totp(secret, _code_for_step(secret, step + 1), for_time=now) == step + 1
    assert verify_totp(secret, _code_for_step(secret, step - 2), for_time=now) is None       # too old
    assert verify_totp(secret, _code_for_step(secret, step + 2), for_time=now) is None       # too new
    assert verify_totp(secret, code, last_step=step, for_time=now) is None                   # already used
    assert verify_totp(secret, code, last_step=step - 1, for_time=now) == step
    for bad in ("", "12345", "1234567", "abcdef", "12 456", "١٢٣٤٥٦"):
        assert verify_totp(secret, bad, for_time=now) is None


def test_provisioning_uri_is_authenticator_compatible():
    uri = provisioning_uri("JBSWY3DPEHPK3PXP", "a@b.gov.in", "MaapSetu")
    assert uri.startswith("otpauth://totp/MaapSetu%3Aa%40b.gov.in?")
    assert "secret=JBSWY3DPEHPK3PXP" in uri and "issuer=MaapSetu" in uri
    assert "digits=6" in uri and f"period={TOTP_PERIOD}" in uri and "algorithm=SHA1" in uri


def test_secrets_are_encrypted_and_recovery_codes_are_well_formed():
    secret = generate_secret()
    token = encrypt_secret(secret)
    assert secret not in token and decrypt_secret(token) == secret
    assert decrypt_secret("not-a-valid-token") is None

    codes = generate_recovery_codes()
    assert len(codes) == 8 and len(set(codes)) == 8
    assert all(len(c) == 11 and c[5] == "-" for c in codes)
    # copy/paste tolerance: case, dashes and spaces don't matter
    assert hash_recovery_code(codes[0]) == hash_recovery_code(codes[0].upper().replace("-", " "))
    assert hash_recovery_code(codes[0]) != hash_recovery_code(codes[1])

    uri = qr_data_uri("otpauth://totp/x")
    assert uri.startswith("data:image/png;base64,")
    assert base64.b64decode(uri.split(",", 1)[1])[:4] == b"\x89PNG"


# ================================================================ login gate


@pytest.mark.parametrize("role", ["lmo", "gatc", "admin"])
def test_password_alone_never_gives_officers_a_session(client, role):
    creds = _seed(role, f"{role}@gate.example.com")
    r = client.post("/api/v1/auth/login", json={"email": creds["email"], "password": creds["password"]})
    body = r.json()
    assert r.status_code == 200
    assert body["mfa_setup_required"] is True and body["mfa_required"] is False
    assert body["token"] is None and body["user"] is None and body["mfa_token"]
    assert not [h for h in r.headers.get_list("set-cookie") if h.startswith("refresh_token=")]


def test_enrolled_officer_is_asked_for_a_code(client):
    body = _step1(client, _seed(mfa=True))
    assert body["mfa_required"] is True and body["mfa_setup_required"] is False
    assert body["token"] is None and body["mfa_token"]


def test_owner_login_is_unchanged(client, registered_owner):
    body = client.post("/api/v1/auth/login", json=registered_owner).json()
    assert body["token"] and body["mfa_required"] is False and body["mfa_setup_required"] is False


def test_wrong_password_never_reaches_the_second_step(client):
    creds = _seed(mfa=True)
    r = client.post("/api/v1/auth/login", json={"email": creds["email"], "password": "wrong"})
    assert r.status_code == 401 and "mfa_token" not in r.json()


def test_mfa_token_cannot_be_used_as_a_login_token(client):
    token = _step1(client, _seed(mfa=True))["mfa_token"]
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_password_step_is_audited(client):
    _step1(client, _seed("admin", "a@gate.example.com"))
    _step1(client, _seed("lmo", "l@gate.example.com", mfa=True))
    details = [e["detail"] for e in _audit("login_password_verified")]
    assert details == ["mfa_setup_required", "mfa_required"]


# ============================================================== enrolment


def test_full_enrolment_flow(client):
    creds = _seed("gatc", "gatc@enrol.example.com")
    mfa_token = _step1(client, creds)["mfa_token"]

    setup = client.post("/api/v1/auth/mfa/setup", json={"mfa_token": mfa_token})
    assert setup.status_code == 200
    s = setup.json()
    assert s["otpauth_uri"].startswith("otpauth://totp/MaapSetu") and s["qr_data_uri"].startswith("data:image/png")
    assert not _user(creds).get("mfa_enabled")  # not on until a code is proven

    done = client.post("/api/v1/auth/mfa/confirm-setup", json={"mfa_token": mfa_token, "code": totp_at(s["secret"])})
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["token"] and body["user"]["mfa_enabled"] is True and body["remember_me"] is False
    assert len(body["recovery_codes"]) == 8
    assert client.get("/api/v1/auth/me", headers=_bearer(done)).status_code == 200

    # stored encrypted + hashed — never in the clear
    doc = _user(creds)
    assert doc["mfa_enabled"] is True and "mfa_pending_secret" not in doc
    assert s["secret"] not in str(doc) and decrypt_secret(doc["mfa_secret_enc"]) == s["secret"]
    assert len(doc["mfa_recovery_hashes"]) == 8
    assert not any(c in str(doc) for c in body["recovery_codes"])

    events = [(e["event"], e["detail"]) for e in _audit() if e["event"] in ("mfa_setup_started", "mfa_enabled", "login_success")]
    assert events == [("mfa_setup_started", None), ("mfa_enabled", None), ("login_success", "mfa_setup")]

    # from now on a code is required
    assert _step1(client, creds)["mfa_required"] is True


def test_refresh_cookie_after_enrolment_is_mfa_verified(client):
    creds = _seed()
    t = _step1(client, creds)["mfa_token"]
    secret = client.post("/api/v1/auth/mfa/setup", json={"mfa_token": t}).json()["secret"]
    done = client.post("/api/v1/auth/mfa/confirm-setup", json={"mfa_token": t, "code": totp_at(secret)})
    client.cookies.clear()
    assert client.post("/api/v1/auth/refresh", cookies=done.cookies).status_code == 200


def test_setup_is_idempotent_so_double_clicks_dont_desync(client):
    t = _step1(client, _seed())["mfa_token"]
    first = client.post("/api/v1/auth/mfa/setup", json={"mfa_token": t}).json()
    second = client.post("/api/v1/auth/mfa/setup", json={"mfa_token": t}).json()
    assert first["secret"] == second["secret"]


def test_wrong_code_does_not_enable_and_counts_toward_lockout(client):
    creds = _seed()
    t = _step1(client, creds)["mfa_token"]
    secret = client.post("/api/v1/auth/mfa/setup", json={"mfa_token": t}).json()["secret"]
    r = client.post("/api/v1/auth/mfa/confirm-setup", json={"mfa_token": t, "code": _wrong(totp_at(secret))})
    assert r.status_code == 401
    doc = _user(creds)
    assert not doc.get("mfa_enabled") and doc["failed_login_attempts"] == 1
    assert _audit("mfa_failed")[-1]["detail"] == "setup_wrong_code"


def test_stale_pending_setup_is_refused(client):
    import app.config.db as dbmod

    creds = _seed()
    t = _step1(client, creds)["mfa_token"]
    secret = client.post("/api/v1/auth/mfa/setup", json={"mfa_token": t}).json()["secret"]
    dbmod.users_col.update_one({"_id": creds["_id"]}, {"$set": {"mfa_pending_at": datetime.now(timezone.utc) - timedelta(hours=1)}})
    r = client.post("/api/v1/auth/mfa/confirm-setup", json={"mfa_token": t, "code": totp_at(secret)})
    assert r.status_code == 400 and "expired" in r.json()["detail"].lower()


def test_confirm_without_starting_setup_is_refused(client):
    t = _step1(client, _seed())["mfa_token"]
    assert client.post("/api/v1/auth/mfa/confirm-setup", json={"mfa_token": t, "code": "123456"}).status_code == 400


def test_cannot_re_enrol_an_account_that_already_has_an_authenticator(client):
    creds = _seed(mfa=True)
    verify_token = _step1(client, creds)["mfa_token"]
    # a verify-purpose token is not valid for setup...
    assert client.post("/api/v1/auth/mfa/setup", json={"mfa_token": verify_token}).status_code == 401
    # ...and a (forged-by-the-test) setup token is refused because MFA is already on.
    from app.utils.security import create_mfa_token

    setup_token = create_mfa_token(str(creds["_id"]), 0, "setup")
    assert client.post("/api/v1/auth/mfa/setup", json={"mfa_token": setup_token}).status_code == 400
    assert client.post("/api/v1/auth/mfa/confirm-setup", json={"mfa_token": setup_token, "code": "123456"}).status_code == 400


# ================================================================ verifying


def test_correct_code_completes_login(client):
    creds = _seed(mfa=True)
    r = full_login(client, creds)
    body = r.json()
    assert body["token"] and body["user"]["email"] == creds["email"] and body["remember_me"] is False
    assert client.get("/api/v1/auth/me", headers=_bearer(r)).status_code == 200
    assert _audit("login_success")[-1]["detail"] == "mfa_totp"
    cookie = [h for h in r.headers.get_list("set-cookie") if h.startswith("refresh_token=")][0].lower()
    assert "max-age" not in cookie


def test_wrong_code_is_rejected_and_audited(client):
    creds = _seed(mfa=True)
    t = _step1(client, creds)["mfa_token"]
    r = client.post("/api/v1/auth/mfa/verify", json={"mfa_token": t, "code": _wrong(fresh_code(creds["_id"], creds["mfa_secret"]))})
    assert r.status_code == 401 and "token" not in r.json()
    ev = _audit("mfa_failed")[-1]
    assert ev["detail"] == "wrong_code" and ev["outcome"] == "failure"


def test_a_code_cannot_be_used_twice(client):
    creds = _seed(mfa=True)
    t = _step1(client, creds)["mfa_token"]
    code = fresh_code(creds["_id"], creds["mfa_secret"])
    assert client.post("/api/v1/auth/mfa/verify", json={"mfa_token": t, "code": code}).status_code == 200
    again = client.post("/api/v1/auth/mfa/verify", json={"mfa_token": t, "code": code})
    assert again.status_code == 401
    assert _audit("mfa_failed")[-1]["detail"] == "wrong_code"  # the step is now behind mfa_last_step


def test_concurrent_claim_of_one_time_step_is_atomic(client):
    """Even if verify_totp() says yes, the DB claim lets only one request win."""
    import app.config.db as dbmod

    creds = _seed(mfa=True)
    step = current_step()
    dbmod.users_col.update_one({"_id": creds["_id"]}, {"$set": {"mfa_last_step": step - 2}})
    claim = lambda: dbmod.users_col.update_one(  # noqa: E731
        {"_id": creds["_id"], "$or": [{"mfa_last_step": {"$lt": step}}, {"mfa_last_step": {"$exists": False}}]},
        {"$set": {"mfa_last_step": step}},
    ).modified_count
    assert (claim(), claim()) == (1, 0)


def test_token_for_the_wrong_step_is_refused(client):
    creds = _seed()  # not enrolled -> setup token
    setup_token = _step1(client, creds)["mfa_token"]
    r = client.post("/api/v1/auth/mfa/verify", json={"mfa_token": setup_token, "code": "123456"})
    assert r.status_code == 401


def test_expired_and_forged_tokens_are_refused(client):
    creds = _seed(mfa=True)
    payload = {"sub": str(creds["_id"]), "tv": 0, "purpose": "verify", "type": "mfa"}
    expired = jwt.encode({**payload, "exp": datetime.now(timezone.utc) - timedelta(minutes=1)}, JWT_SECRET, algorithm=JWT_ALGORITHM)
    r = client.post("/api/v1/auth/mfa/verify", json={"mfa_token": expired, "code": "123456"})
    assert r.status_code == 401 and "expired" in r.json()["detail"].lower()

    forged = jwt.encode({**payload, "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, "not-the-real-secret", algorithm=JWT_ALGORITHM)
    assert client.post("/api/v1/auth/mfa/verify", json={"mfa_token": forged, "code": "123456"}).status_code == 401
    assert client.post("/api/v1/auth/mfa/verify", json={"mfa_token": "garbage", "code": "123456"}).status_code == 401

    # an ordinary ACCESS token is not an MFA token either
    from app.utils.security import create_access_token

    access = create_access_token(str(creds["_id"]), 0)
    assert client.post("/api/v1/auth/mfa/verify", json={"mfa_token": access, "code": "123456"}).status_code == 401


def test_mfa_token_dies_when_the_password_changes_or_sessions_are_revoked(client):
    import app.config.db as dbmod

    creds = _seed(mfa=True)
    t = _step1(client, creds)["mfa_token"]
    dbmod.users_col.update_one({"_id": creds["_id"]}, {"$inc": {"token_version": 1}})
    r = client.post("/api/v1/auth/mfa/verify", json={"mfa_token": t, "code": fresh_code(creds["_id"], creds["mfa_secret"])})
    assert r.status_code == 401


def test_mfa_token_for_an_owner_or_inactive_account_is_refused(client):
    from app.utils.security import create_mfa_token

    owner = _seed("owner", "biz@example.com")
    t = create_mfa_token(str(owner["_id"]), 0, "setup")
    assert client.post("/api/v1/auth/mfa/setup", json={"mfa_token": t}).status_code == 401

    suspended = _seed("lmo", "sus@example.com", mfa=True, status="rejected")
    t2 = create_mfa_token(str(suspended["_id"]), 0, "verify")
    r = client.post("/api/v1/auth/mfa/verify", json={"mfa_token": t2, "code": fresh_code(suspended["_id"], suspended["mfa_secret"])})
    assert r.status_code == 401


def test_repeated_wrong_codes_lock_the_account_even_for_the_right_code(client):
    creds = _seed(mfa=True)
    t = _step1(client, creds)["mfa_token"]
    bad = _wrong(fresh_code(creds["_id"], creds["mfa_secret"]))
    for _ in range(LOGIN_MAX_ATTEMPTS):
        assert client.post("/api/v1/auth/mfa/verify", json={"mfa_token": t, "code": bad}).status_code == 401
    assert _audit("mfa_failed")[-1]["detail"] == "wrong_code_account_locked"

    right = fresh_code(creds["_id"], creds["mfa_secret"])
    locked = client.post("/api/v1/auth/mfa/verify", json={"mfa_token": t, "code": right})
    assert locked.status_code == 429
    assert _audit("mfa_blocked")[-1]["detail"] == "account_locked"
    # the password step is locked out too
    assert client.post("/api/v1/auth/login", json={"email": creds["email"], "password": creds["password"]}).status_code == 429


def test_password_step_does_not_reset_the_failed_attempt_counter(client):
    """Otherwise an attacker who knows the password could log in, miss a code,
    log in again (counter reset), miss again... and never get locked out."""
    creds = _seed(mfa=True)
    for _ in range(3):
        t = _step1(client, creds)["mfa_token"]
        client.post("/api/v1/auth/mfa/verify", json={"mfa_token": t, "code": _wrong(fresh_code(creds["_id"], creds["mfa_secret"]))})
    assert _user(creds)["failed_login_attempts"] == 3
    full_login(client, creds)
    assert _user(creds)["failed_login_attempts"] == 0   # cleared only by a full success


# ============================================================ recovery codes


def test_recovery_code_works_once_and_reports_how_many_remain(client):
    creds = _seed(mfa=True)  # enroll_mfa gives two codes: aaaaa-bbbbb, ccccc-ddddd
    t = _step1(client, creds)["mfa_token"]
    r = client.post("/api/v1/auth/mfa/verify", json={"mfa_token": t, "code": "AAAAA-BBBBB"})  # case-insensitive
    assert r.status_code == 200, r.text
    assert r.json()["recovery_codes_remaining"] == 1 and r.json()["token"]
    assert _audit("login_success")[-1]["detail"] == "mfa_recovery_code"

    t2 = _step1(client, creds)["mfa_token"]
    again = client.post("/api/v1/auth/mfa/verify", json={"mfa_token": t2, "code": "aaaaa-bbbbb"})
    assert again.status_code == 401
    other = client.post("/api/v1/auth/mfa/verify", json={"mfa_token": t2, "code": "ccccc ddddd"})  # spaces instead of dash
    assert other.status_code == 200 and other.json()["recovery_codes_remaining"] == 0


def test_totp_login_does_not_report_recovery_count(client):
    assert full_login(client, _seed(mfa=True)).json()["recovery_codes_remaining"] is None


# ================================================= sessions need the 2nd step


def test_refresh_is_refused_for_officer_sessions_that_skipped_the_second_step(client):
    """e.g. a refresh token issued before two-step verification existed."""
    import app.config.db as dbmod
    from app.utils.security import generate_refresh_token, hash_refresh_token

    creds = _seed(mfa=True)
    raw = generate_refresh_token()
    dbmod.refresh_tokens_col.insert_one({
        "user_id": str(creds["_id"]), "token_hash": hash_refresh_token(raw), "revoked": False,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=1), "created_at": datetime.now(timezone.utc),
    })
    client.cookies.clear()
    r = client.post("/api/v1/auth/refresh", cookies={"refresh_token": raw})
    assert r.status_code == 401
    assert _audit("refresh_rejected")[-1]["detail"] == "mfa_not_verified"


def test_verified_officer_session_can_refresh_and_stays_verified(client):
    first = full_login(client, _seed(mfa=True))
    client.cookies.clear()
    second = client.post("/api/v1/auth/refresh", cookies=first.cookies)
    assert second.status_code == 200
    client.cookies.clear()
    assert client.post("/api/v1/auth/refresh", cookies=second.cookies).status_code == 200  # still verified after rotation


def test_change_password_keeps_the_officers_session_mfa_verified(client):
    creds = _seed(mfa=True)
    login = full_login(client, creds)
    client.cookies.clear()
    r = client.post("/api/v1/auth/change-password", headers=_bearer(login), cookies=login.cookies,
                    json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert r.status_code == 200, r.text
    client.cookies.clear()
    assert client.post("/api/v1/auth/refresh", cookies=r.cookies).status_code == 200


def test_owner_refresh_does_not_need_mfa(client, registered_owner):
    login = client.post("/api/v1/auth/login", json=registered_owner)
    client.cookies.clear()
    assert client.post("/api/v1/auth/refresh", cookies=login.cookies).status_code == 200


def test_refresh_is_refused_for_a_suspended_account(client):
    import app.config.db as dbmod

    creds = _seed(mfa=True)
    login = full_login(client, creds)
    dbmod.users_col.update_one({"_id": creds["_id"]}, {"$set": {"status": "rejected"}})
    client.cookies.clear()
    assert client.post("/api/v1/auth/refresh", cookies=login.cookies).status_code == 401
    assert _audit("refresh_rejected")[-1]["detail"] == "account_not_active"


# ============================================ admin controls + lifecycle audit


@pytest.fixture
def admin_headers(client, monkeypatch):
    import app.config.db as dbmod
    import app.routers.admin_users as admin_mod

    # The admin router imported these collections by name, so point them at the in-memory DB too.
    monkeypatch.setattr(admin_mod, "users_col", dbmod.db["users"])
    monkeypatch.setattr(admin_mod, "refresh_tokens_col", dbmod.db["refresh_tokens"])
    monkeypatch.setattr(admin_mod, "otp_verifications_col", dbmod.db["otp_verifications"])
    dbmod.db["users"].create_index("email", unique=True)  # production has this index; DuplicateKeyError relies on it
    admin = _seed("admin", "boss@example.com", mfa=True)
    return admin, {"Authorization": f"Bearer {full_login(client, admin).json()['token']}"}


def test_admin_can_reset_an_officers_two_step_verification(client, admin_headers):
    admin, h = admin_headers
    officer = _seed("lmo", "off@example.com", mfa=True)
    officer_session = full_login(client, officer)

    r = client.post(f"/api/v1/admin/users/{officer['_id']}/reset-mfa", headers=h)
    assert r.status_code == 200 and r.json()["mfa_enabled"] is False

    doc = _user(officer)
    assert doc["mfa_enabled"] is False and not any(k in doc for k in ("mfa_secret_enc", "mfa_recovery_hashes", "mfa_last_step"))
    # signed out everywhere
    assert client.get("/api/v1/auth/me", headers=_bearer(officer_session)).status_code == 401
    client.cookies.clear()
    assert client.post("/api/v1/auth/refresh", cookies=officer_session.cookies).status_code == 401
    # next sign-in asks them to enrol again; the old secret no longer works
    assert _step1(client, officer)["mfa_setup_required"] is True

    ev = _audit("mfa_reset")[-1]
    assert ev["actor_id"] == str(admin["_id"]) and ev["email"] == officer["email"]


def test_reset_mfa_is_admin_only_and_officers_only(client, admin_headers):
    admin, h = admin_headers
    officer = _seed("lmo", "off2@example.com", mfa=True)
    other_admin = _seed("admin", "boss2@example.com", mfa=True)
    owner = _seed("owner", "biz@example.com")

    assert client.post(f"/api/v1/admin/users/{other_admin['_id']}/reset-mfa", headers=h).status_code == 400
    assert client.post(f"/api/v1/admin/users/{owner['_id']}/reset-mfa", headers=h).status_code == 400
    assert client.post("/api/v1/admin/users/not-an-id/reset-mfa", headers=h).status_code == 400
    assert client.post("/api/v1/admin/users/64b000000000000000000000/reset-mfa", headers=h).status_code == 404

    officer_h = {"Authorization": f"Bearer {full_login(client, officer).json()['token']}"}
    assert client.post(f"/api/v1/admin/users/{officer['_id']}/reset-mfa", headers=officer_h).status_code == 403
    assert client.post(f"/api/v1/admin/users/{officer['_id']}/reset-mfa").status_code in (401, 403)
    assert _user(other_admin)["mfa_enabled"] is True


def test_officer_list_shows_who_has_two_step_enabled(client, admin_headers):
    _, h = admin_headers
    _seed("lmo", "has@example.com", mfa=True)
    _seed("gatc", "hasnt@example.com")
    rows = {u["email"]: u["mfa_enabled"] for u in client.get("/api/v1/admin/users", headers=h).json()}
    assert rows == {"has@example.com": True, "hasnt@example.com": False}


def test_operator_script_clears_mfa_and_revokes_sessions(client, monkeypatch):
    import app.config.db as dbmod
    import reset_mfa

    monkeypatch.setattr(reset_mfa, "users_col", dbmod.db["users"])
    monkeypatch.setattr(reset_mfa, "refresh_tokens_col", dbmod.db["refresh_tokens"])
    admin = _seed("admin", "minister@example.com", mfa=True)
    session = full_login(client, admin)

    monkeypatch.setattr("sys.argv", ["reset_mfa.py", "Minister@Example.com"])
    reset_mfa.main()

    assert _user(admin)["mfa_enabled"] is False
    assert client.get("/api/v1/auth/me", headers=_bearer(session)).status_code == 401
    ev = _audit("mfa_reset")[-1]
    assert ev["actor_id"] == "operator-script" and ev["email"] == "minister@example.com"

    monkeypatch.setattr("sys.argv", ["reset_mfa.py", "nobody@example.com"])
    with pytest.raises(SystemExit):
        reset_mfa.main()


def test_suspending_an_officer_ends_their_sessions_and_is_audited(client, admin_headers):
    admin, h = admin_headers
    officer = _seed("lmo", "sus@example.com", mfa=True)
    session = full_login(client, officer)

    r = client.post(f"/api/v1/admin/users/{officer['_id']}/reject", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "rejected"

    assert client.get("/api/v1/auth/me", headers=_bearer(session)).status_code == 401   # access token dead
    client.cookies.clear()
    assert client.post("/api/v1/auth/refresh", cookies=session.cookies).status_code == 401  # can't renew
    assert client.post("/api/v1/auth/login", json={"email": officer["email"], "password": PASSWORD}).status_code == 403

    ev = _audit("account_suspended")[-1]
    assert ev["actor_id"] == str(admin["_id"]) and ev["email"] == officer["email"] and ev["detail"] == "from=active"


def test_approving_an_officer_is_audited(client, admin_headers):
    admin, h = admin_headers
    officer = _seed("gatc", "pend@example.com", status="pending")
    r = client.post(f"/api/v1/admin/users/{officer['_id']}/approve", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "active"
    ev = _audit("account_approved")[-1]
    assert ev["actor_id"] == str(admin["_id"]) and ev["detail"] == "from=pending" and ev["role"] == "gatc"


def test_officer_creation_is_audited(client, admin_headers, monkeypatch):
    import app.config.db as dbmod
    import app.routers.admin_users as admin_mod

    monkeypatch.setattr(admin_mod, "states_col", dbmod.db["states"])
    monkeypatch.setattr(admin_mod, "districts_col", dbmod.db["districts"])
    monkeypatch.setattr(admin_mod, "smtp_is_configured", lambda: False)
    dbmod.db["states"].insert_one({"code": "WB", "name": "West Bengal"})
    dbmod.db["districts"].insert_one({"code": "319", "state_code": "WB", "name": "Kolkata"})
    admin, h = admin_headers

    body = {"name": "New Officer", "email": "newoff@example.com", "role": "lmo", "contact": "9876543210",
            "jurisdiction": {"state_code": "WB", "district_code": "319"}}
    ok = client.post("/api/v1/admin/users/create-officer", headers=h, json=body)
    assert ok.status_code == 201, ok.text
    ev = _audit("officer_created")[-1]
    assert ev["actor_id"] == str(admin["_id"]) and ev["email"] == "newoff@example.com"
    assert ev["role"] == "lmo" and ev["detail"] == "jurisdiction=WB/319" and ev["user_id"] == ok.json()["user"]["id"]
    assert ok.json()["temp_password"] not in str(_audit())

    dup = client.post("/api/v1/admin/users/create-officer", headers=h, json=body)
    assert dup.status_code == 409
    bad_state = client.post("/api/v1/admin/users/create-officer", headers=h,
                            json={**body, "email": "x@example.com", "jurisdiction": {"state_code": "ZZ"}})
    assert bad_state.status_code == 400
    bad_role = client.post("/api/v1/admin/users/create-officer", headers=h, json={**body, "email": "y@example.com", "role": "admin"})
    assert bad_role.status_code == 400
    assert [e["detail"] for e in _audit("officer_creation_failed")] == ["email_exists", "unknown_state", "invalid_role"]


def test_registration_is_audited(client, monkeypatch):
    import app.config.db as dbmod
    import app.services.otp as otp_mod

    monkeypatch.setattr(otp_mod, "otp_verifications_col", dbmod.db["otp_verifications"])
    dbmod.db["users"].create_index("email", unique=True)
    base = {"name": "Asha Rao", "email": "asha@example.com", "password": "Str0ng!Passw0rd", "role": "owner",
            "org_name": "Asha Traders", "contact": "9876543210"}

    # not verified yet
    assert client.post("/api/v1/auth/register", json=base).status_code == 400
    # officer role self-registration attempt
    assert client.post("/api/v1/auth/register", json={**base, "role": "admin"}).status_code == 403

    def proof():
        dbmod.db["otp_verifications"].insert_one({
            "identifier": "asha@example.com", "purpose": "email_verify", "verified": True,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10)})

    proof()
    ok = client.post("/api/v1/auth/register", json=base)
    assert ok.status_code == 201, ok.text
    proof()
    assert client.post("/api/v1/auth/register", json=base).status_code == 409

    registered = _audit("account_registered")
    assert len(registered) == 1 and registered[0]["email"] == "asha@example.com"
    assert registered[0]["role"] == "owner" and registered[0]["user_id"] == ok.json()["user"]["id"]
    assert "Str0ng!Passw0rd" not in str(_audit())

    failures = [(e["outcome"], e["detail"]) for e in _audit("account_registration_failed")]
    assert failures == [("failure", "email_not_verified"), ("blocked", "role_not_allowed:admin"), ("failure", "email_exists")]
