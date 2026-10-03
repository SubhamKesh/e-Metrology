"""Test helpers for accounts that must use two-step verification."""
from datetime import datetime, timezone

from app.utils.mfa import encrypt_secret, hash_recovery_code
from app.utils.totp import current_step, generate_secret, totp_at


def enroll_mfa(user_id, recovery_codes=("aaaaa-bbbbb", "ccccc-ddddd")) -> str:
    """Directly marks `user_id` as having an authenticator set up (as if they had
    completed enrolment) and returns the base32 secret so tests can generate codes."""
    import app.config.db as dbmod

    secret = generate_secret()
    dbmod.users_col.update_one(
        {"_id": user_id},
        {
            "$set": {
                "mfa_enabled": True,
                "mfa_secret_enc": encrypt_secret(secret),
                "mfa_enabled_at": datetime.now(timezone.utc),
                "mfa_last_step": current_step() - 2,
                "mfa_recovery_hashes": [hash_recovery_code(c) for c in recovery_codes],
            }
        },
    )
    return secret


def fresh_code(user_id, secret) -> str:
    """A valid code for the current time step. Rewinds the replay guard first so a
    test can sign the same user in several times within one 30-second step —
    tests about replay protection manage `mfa_last_step` themselves instead."""
    import app.config.db as dbmod

    dbmod.users_col.update_one({"_id": user_id}, {"$set": {"mfa_last_step": current_step() - 2}})
    return totp_at(secret)


def full_login(client, creds, **login_extra):
    """Password step + second step for an account with creds['mfa_secret'].
    Returns the /auth/mfa/verify response (it carries the token and cookie)."""
    client.cookies.clear()
    step1 = client.post(
        "/api/v1/auth/login",
        json={"email": creds["email"], "password": creds["password"], **login_extra},
    )
    assert step1.status_code == 200, step1.text
    body = step1.json()
    assert body["mfa_required"] is True and body["token"] is None, body
    step2 = client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": body["mfa_token"], "code": fresh_code(creds["_id"], creds["mfa_secret"])},
    )
    assert step2.status_code == 200, step2.text
    return step2
