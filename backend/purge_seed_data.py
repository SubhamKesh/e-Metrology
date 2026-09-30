"""
Removes the demo records created by seed/seed.py from the database that
MONGO_URI points at -- and nothing else.

What it matches (all taken from seed/seed_data.py, nothing guessed):
  * the seeded users, by their exact email addresses
  * instruments / applications owned by those users
  * inspections of those applications
  * certificates with the seeded ids, or belonging to those applications /
    instruments
  * alerts for those users, and those users' refresh tokens

Real accounts and everything they created are left alone.

Safe by default: with no flags it only PRINTS what it would delete.

    cd backend
    python purge_seed_data.py              # dry run, deletes nothing
    python purge_seed_data.py --yes        # actually delete

The seeded admin (admin@legalmetrology.gov.in, password "seed-pass-006" -- it
is in the public repo) is skipped unless you also pass --include-admins, and
even then only if some OTHER active admin exists, so you can't lock yourself
out. Create your real admin first with seed_super_admin.py.

Point MONGO_URI at the database you mean to clean (e.g. your Atlas URI in
backend/.env) before running, and check the counts in the dry run first.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app.config.db import (  # noqa: E402
    alerts_col,
    applications_col,
    certificates_col,
    inspections_col,
    instruments_col,
    refresh_tokens_col,
    users_col,
)
from seed.seed_data import CERTIFICATES, USERS  # noqa: E402

SEED_EMAILS = [u["email"] for u in USERS]
SEED_CERT_IDS = [c["id"] for c in CERTIFICATES]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="actually delete (default is a dry run)")
    parser.add_argument("--include-admins", action="store_true", help="also delete the seeded admin account")
    args = parser.parse_args()

    from app.config.settings import DB_NAME

    print(f"Database: {DB_NAME}")
    print("Mode:     " + ("DELETE" if args.yes else "dry run (nothing will be deleted)"))
    print()

    seeded_users = list(users_col.find({"email": {"$in": SEED_EMAILS}}))
    seeded_admins = [u for u in seeded_users if u.get("role") == "admin"]
    to_delete_users = [u for u in seeded_users if u.get("role") != "admin"]

    skipped_admin_note = None
    if seeded_admins:
        if not args.include_admins:
            skipped_admin_note = (
                "Seeded admin account(s) kept (pass --include-admins to remove): "
                + ", ".join(u["email"] for u in seeded_admins)
            )
        else:
            other_admin = users_col.find_one(
                {"role": "admin", "email": {"$nin": SEED_EMAILS}, "status": {"$ne": "rejected"}}
            )
            if other_admin is None:
                print("REFUSING to delete the seeded admin: no other admin account exists, you would be locked out.")
                print("Run seed_super_admin.py first, then re-run with --include-admins.")
                return 1
            to_delete_users += seeded_admins

    user_ids = [u["_id"] for u in to_delete_users]
    owner_ids = [u["_id"] for u in to_delete_users if u.get("role") == "owner"]

    instruments = list(instruments_col.find({"owner_id": {"$in": owner_ids}}, {"_id": 1}))
    instrument_ids = [i["_id"] for i in instruments]
    applications = list(applications_col.find({"owner_id": {"$in": owner_ids}}, {"_id": 1}))
    application_ids = [a["_id"] for a in applications]

    cert_filter = {
        "$or": [
            {"_id": {"$in": SEED_CERT_IDS}},
            {"application_id": {"$in": application_ids}},
            {"instrument_id": {"$in": instrument_ids}},
        ]
    }
    insp_filter = {"application_id": {"$in": application_ids}}
    alert_filter = {"owner_id": {"$in": owner_ids}}
    token_filter = {"user_id": {"$in": [str(i) for i in user_ids]}}

    plan = [
        ("certificates", certificates_col, cert_filter),
        ("inspections", inspections_col, insp_filter),
        ("applications", applications_col, {"_id": {"$in": application_ids}}),
        ("instruments", instruments_col, {"_id": {"$in": instrument_ids}}),
        ("alerts", alerts_col, alert_filter),
        ("refresh_tokens", refresh_tokens_col, token_filter),
        ("users", users_col, {"_id": {"$in": user_ids}}),
    ]

    print("Would delete:" if not args.yes else "Deleting:")
    for label, col, flt in plan:
        count = col.count_documents(flt)
        if args.yes and count:
            count = col.delete_many(flt).deleted_count
        print(f"  {label:<15} {count}")

    # Things deliberately NOT touched, worth a look.
    officer_ids = [u["_id"] for u in seeded_users if u.get("role") in ("lmo", "gatc")]
    stray = applications_col.count_documents(
        {"assigned_officer_id": {"$in": officer_ids}, "_id": {"$nin": application_ids}}
    )
    print()
    if skipped_admin_note:
        print("NOTE: " + skipped_admin_note)
        print("      Its password is public (seed-pass-006). Rotate it or remove it once your real admin works.")
    if stray:
        print(f"NOTE: {stray} real application(s) are assigned to a seeded officer and were left alone; reassign them.")
    if not args.yes:
        print("\nDry run only. Re-run with --yes to delete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
