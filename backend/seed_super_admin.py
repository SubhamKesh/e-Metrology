"""
Seeds (or updates) the single super-admin account — the Minister / head of
the Legal Metrology department. This account is never created through the
normal /auth/register flow (that route explicitly rejects role="admin");
it only ever comes from this script.

Why a script instead of hardcoding the password in code:
  - The password itself lives only in your environment (.env), never in
    source control / git history, and is hashed with bcrypt before it ever
    touches the database — same as every other user's password.
  - Re-running this script is safe: if the account already exists, it just
    updates the password hash (e.g. if you rotate the password later)
    instead of failing on a duplicate-email error.

Setup, in backend/.env:
    SUPER_ADMIN_EMAIL=minister@legalmetrology.gov.in
    SUPER_ADMIN_PASSWORD=some-long-random-string
    SUPER_ADMIN_NAME=Minister of Legal Metrology

Run once (or again, any time you want to rotate the password), from the
backend/ directory with your venv active:

    python seed_super_admin.py

The minister then logs in through the normal POST /api/v1/auth/login
endpoint like anyone else — there is no special-cased login path for this
account, it's a completely ordinary "admin"-role user under the hood.
"""

import os
import sys

from app.config.db import users_col
from app.utils.security import hash_password


def main() -> None:
    email = os.getenv("SUPER_ADMIN_EMAIL")
    password = os.getenv("SUPER_ADMIN_PASSWORD")
    name = os.getenv("SUPER_ADMIN_NAME", "Minister of Legal Metrology")

    if not email or not password:
        print("SUPER_ADMIN_EMAIL and SUPER_ADMIN_PASSWORD must be set in your .env file.")
        sys.exit(1)

    if len(password) < 12:
        print("SUPER_ADMIN_PASSWORD is short for a top-level account — consider a longer, random value.")

    email = email.lower()
    existing = users_col.find_one({"email": email})

    doc = {
        "name": name,
        "email": email,
        "password": hash_password(password),
        "role": "admin",
        "status": "active",
        "org_type": None,
        "org_name": "Ministry of Legal Metrology",
        "contact": None,
    }

    if existing:
        users_col.update_one({"_id": existing["_id"]}, {"$set": doc})
        print(f"Updated existing super-admin account: {email}")
    else:
        users_col.insert_one(doc)
        print(f"Created super-admin account: {email}")


if __name__ == "__main__":
    main()
