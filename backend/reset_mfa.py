"""
Operator tool: clears an account's two-step verification so its owner can
enrol a new authenticator at their next sign-in.

When you need this
  - The super admin lost their phone AND their recovery codes. (Officers
    don't need it: an admin resets an officer from Admin -> Officer accounts.)

Why it's a script and not an API endpoint
  - Anyone who can run this already has access to the server/database, which
    is a stronger position than any web session. Keeping it out of the API
    means a hijacked admin session can never strip another admin's second
    factor.

Run from the backend/ directory with your venv active and .env loaded:

    python reset_mfa.py minister@legalmetrology.gov.in

It also signs the account out of every session, and writes an `mfa_reset`
record to the audit log (actor: "operator-script").
"""

import sys

from app.config.db import users_col, refresh_tokens_col
from app.services.audit import log_event


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python reset_mfa.py <account-email>")
        sys.exit(2)

    email = sys.argv[1].strip().lower()
    user = users_col.find_one({"email": email})
    if not user:
        print(f"No account with email {email!r}.")
        sys.exit(1)

    users_col.update_one(
        {"_id": user["_id"]},
        {
            "$set": {"mfa_enabled": False},
            "$unset": {
                "mfa_secret_enc": "",
                "mfa_pending_secret": "",
                "mfa_pending_at": "",
                "mfa_last_step": "",
                "mfa_recovery_hashes": "",
                "mfa_enabled_at": "",
            },
            "$inc": {"token_version": 1},
        },
    )
    refresh_tokens_col.update_many({"user_id": str(user["_id"]), "revoked": False}, {"$set": {"revoked": True}})
    log_event(
        "mfa_reset",
        outcome="success",
        email=user["email"],
        user_id=str(user["_id"]),
        role=user.get("role"),
        actor_id="operator-script",
        detail="reset_mfa.py",
    )
    print(f"Two-step verification cleared for {email}; all sessions revoked.")
    print("They will be asked to set up an authenticator at their next sign-in.")


if __name__ == "__main__":
    main()
