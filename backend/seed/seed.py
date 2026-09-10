"""
backend/seed/seed.py

Loads the static data in seed_data.py and actually inserts it into MongoDB,
matching the real schema used by app/config/db.py and app/models/*:

  - Every document gets a real ObjectId as _id (except Certificates, which
    keep their human-readable string id — cert_generator.py does the same,
    using a string _id there too, so this stays consistent).
  - Foreign keys (owner_id, instrument_id, assigned_officer_id, etc.) are
    rewritten from seed_data.py's readable ids ("usr_owner_001") to the
    real ObjectIds generated here.
  - Passwords are hashed through the same function auth uses
    (app/utils/security.py) — never inserted as plaintext.
  - Running this script wipes the 6 collections first, so it's safe to
    run repeatedly while developing (idempotent, not additive).

Usage:
    cd backend
    python -m seed.seed
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from bson import ObjectId

from app.config.db import (
    users_col,
    instruments_col,
    applications_col,
    inspections_col,
    certificates_col,
    alerts_col,
)
from app.utils.security import hash_password
from seed.seed_data import USERS, INSTRUMENTS, APPLICATIONS, INSPECTIONS, CERTIFICATES, ALERTS


def parse_iso(iso_str: str) -> datetime:
    return datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def wipe_collections():
    for col in (users_col, instruments_col, applications_col, inspections_col, certificates_col, alerts_col):
        col.delete_many({})


def seed_users() -> dict:
    """Returns a map of seed_data's readable id -> real ObjectId."""
    id_map = {}
    for u in USERS:
        oid = ObjectId()
        id_map[u["id"]] = oid
        users_col.insert_one({
            "_id": oid,
            "name": u["name"],
            "email": u["email"],
            "password": hash_password(u["password"]),
            "role": u["role"],
            "status": "active",
            "org_type": u["org_type"],
            "org_name": u["org_name"],
            "contact": u["contact"],
        })
    return id_map


def seed_instruments(user_ids: dict) -> dict:
    id_map = {}
    for i in INSTRUMENTS:
        oid = ObjectId()
        id_map[i["id"]] = oid
        instruments_col.insert_one({
            "_id": oid,
            "owner_id": user_ids[i["owner_id"]],
            "type": i["type"],
            "manufacturer": i["manufacturer"],
            "model": i["model"],
            "capacity": i["capacity"],
            "uiid": i["uiid"],
            "location": i["location"],
        })
    return id_map


def seed_applications(user_ids: dict, instrument_ids: dict) -> dict:
    id_map = {}
    for a in APPLICATIONS:
        oid = ObjectId()
        id_map[a["id"]] = oid
        submitted_at = parse_iso(a["submitted_at"])
        # A single synthetic history entry reflecting the current status.
        # Real applications build this incrementally via status_transition.py;
        # seed data just needs something present so GET /applications/{id}
        # doesn't return an empty history[] for demo records.
        history = [{
            "from": None,
            "to": a["status"],
            "at": submitted_at,
            "reason": "seeded directly at this status for demo purposes",
        }]
        applications_col.insert_one({
            "_id": oid,
            "instrument_id": instrument_ids[a["instrument_id"]],
            "owner_id": user_ids[a["owner_id"]],
            "status": a["status"],
            "assigned_officer_id": user_ids[a["assigned_officer_id"]] if a["assigned_officer_id"] else None,
            "submitted_at": submitted_at,
            "history": history,
        })
    return id_map


def seed_inspections(user_ids: dict, application_ids: dict) -> dict:
    id_map = {}
    for insp in INSPECTIONS:
        oid = ObjectId()
        id_map[insp["id"]] = oid
        inspections_col.insert_one({
            "_id": oid,
            "application_id": application_ids[insp["application_id"]],
            "officer_id": user_ids[insp["officer_id"]],
            "observations": insp["observations"],
            "result": insp["result"],
            "photos": insp["photos"],
            "inspected_at": parse_iso(insp["inspected_at"]),
        })
    return id_map


def seed_certificates(application_ids: dict, instrument_ids: dict, inspection_ids: dict):
    """
    Certificates keep their seed_data string id (e.g. "LM-2026-001A") as
    _id, same convention cert_generator.py uses for real ones (a string,
    just a uuid4 there instead of a readable label).
    """
    # Build application_id -> inspection's real ObjectId, since seed_data's
    # CERTIFICATES only reference application_id, not inspection_id directly.
    app_to_inspection = {
        insp["application_id"]: inspection_ids[insp["id"]]
        for insp in INSPECTIONS
    }

    for c in CERTIFICATES:
        certificates_col.insert_one({
            "_id": c["id"],
            "inspection_id": app_to_inspection.get(c["application_id"]),
            "application_id": application_ids[c["application_id"]],
            "instrument_id": instrument_ids[c["instrument_id"]],
            "cert_no": c["id"],
            "qr_url": None,   # not generated for seed data — no real Cloudinary call made
            "pdf_url": None,
            "issued_at": parse_iso(c["verified_on"]),
            "valid_until": parse_iso(c["valid_until"]),
        })


def seed_alerts(user_ids: dict):
    for a in ALERTS:
        alerts_col.insert_one({
            "certificate_id": a["certificate_id"],
            "owner_id": user_ids.get(a["owner_id"]),
            "alert_type": a["type"],
            "message": a["message"],
            "sent_at": parse_iso(a["sent_at"]),
        })


def run():
    print("Wiping existing collections...")
    wipe_collections()

    print("Seeding users...")
    user_ids = seed_users()

    print("Seeding instruments...")
    instrument_ids = seed_instruments(user_ids)

    print("Seeding applications...")
    application_ids = seed_applications(user_ids, instrument_ids)

    print("Seeding inspections...")
    inspection_ids = seed_inspections(user_ids, application_ids)

    print("Seeding certificates...")
    seed_certificates(application_ids, instrument_ids, inspection_ids)

    print("Seeding alerts...")
    seed_alerts(user_ids)

    print()
    print("Done. Counts:")
    print(f"  users:         {users_col.count_documents({})}")
    print(f"  instruments:   {instruments_col.count_documents({})}")
    print(f"  applications:  {applications_col.count_documents({})}")
    print(f"  inspections:   {inspections_col.count_documents({})}")
    print(f"  certificates:  {certificates_col.count_documents({})}")
    print(f"  alerts:        {alerts_col.count_documents({})}")
    print()
    print("All seed users share their seed_data.py passwords (e.g. 'seed-pass-001'),")
    print("now hashed in the DB — log in with the plaintext version from seed_data.py.")


if __name__ == "__main__":
    run()
