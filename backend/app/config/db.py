from pymongo import MongoClient
from pymongo.errors import OperationFailure
from app.config.settings import MONGO_URI, DB_NAME

# maxPoolSize caps concurrent connections this process can open to Atlas —
# without a limit, a traffic spike (or a leak) can exhaust the cluster's
# shared connection limit and take down every service sharing the cluster.
# minPoolSize keeps a few warm so we're not paying handshake cost on every
# burst of requests after an idle period.
client = MongoClient(MONGO_URI, maxPoolSize=50, minPoolSize=5)
db = client[DB_NAME]

# Collections — import these directly wherever you need DB access.
users_col = db["users"]
counters_col = db["counters"]
instruments_col = db["instruments"]
applications_col = db["applications"]
inspections_col = db["inspections"]
certificates_col = db["certificates"]
alerts_col = db["alerts"]
# Refresh tokens live in their own collection so they can be listed/revoked
# per-user (e.g. "log out of all devices") without touching users_col at all.
refresh_tokens_col = db["refresh_tokens"]

# Reference data (seeded by scripts/seed_geo.py) — states/UTs and their
# districts. Kept as data, not code, so a boundary change doesn't need a
# deploy. Every state_code/district_code stored elsewhere in the app is
# validated against these two collections at write time.
states_col = db["states"]
districts_col = db["districts"]


def init_indexes():
    """Call once at startup to make sure key fields are indexed/unique."""
    users_col.create_index("email", unique=True)
    instruments_col.create_index("uiid", unique=True)
    applications_col.create_index("status")
    certificates_col.create_index("cert_no", unique=True)

    # Geo reference lookups.
    states_col.create_index("code", unique=True)
    districts_col.create_index([("state_code", 1), ("code", 1)], unique=True)

    # Jurisdiction-scoped queries. Applications are the hot path — every
    # officer's queue/dashboard query filters by (state_code, district_code)
    # plus either status or a date range, so those go first in the compound
    # index (ESR: equality fields before range fields).
    applications_col.create_index([("state_code", 1), ("district_code", 1), ("status", 1)])
    applications_col.create_index([("state_code", 1), ("district_code", 1), ("submitted_at", -1)])
    instruments_col.create_index([("location.state_code", 1), ("location.district_code", 1)])
    users_col.create_index([("jurisdiction.state_code", 1), ("jurisdiction.district_code", 1)])

    # Refresh-token lookups are always by hash; TTL index lets Mongo garbage
    # collect expired tokens on its own instead of us needing a cron for it.
    refresh_tokens_col.create_index("token_hash", unique=True)
    refresh_tokens_col.create_index("user_id")
    refresh_tokens_col.create_index("expires_at", expireAfterSeconds=0)

    _apply_schema_validation()


# --- DB-level schema validation ($jsonSchema) --------------------------
#
# Pydantic already validates shape at the API boundary, but that only
# covers writes that go through the API. This is a second, independent
# gate enforced by MongoDB itself — so a bad write from a script, a
# migration, or a bug that bypasses a model still gets rejected at the DB.
# `collMod` is used (not `create_collection`) because these collections
# already exist; collMod attaches/updates a validator on an existing one.
# Wrapped in try/except so a permissions-restricted DB user (e.g. a
# least-privilege service account per Section 2 of the checklist, which
# may not be allowed to run collMod) doesn't crash startup — see
# app/main.py's already-existing "don't crash if DB setup fails" pattern.
def _apply_schema_validation():
    validators = {
        "users": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["name", "email", "password", "role", "status"],
                "properties": {
                    "email": {"bsonType": "string"},
                    "password": {"bsonType": "string"},
                    "role": {"enum": ["owner", "lmo", "gatc", "admin"]},
                    "status": {"enum": ["pending", "active", "rejected"]},
                    # jurisdiction.district_code is intentionally not
                    # required here — omitted means state-level scope
                    # (GATC); Pydantic (OfficerCreate) is what actually
                    # enforces state_code being present for lmo/gatc.
                    "jurisdiction": {
                        "bsonType": ["object", "null"],
                        "properties": {
                            "state_code": {"bsonType": "string"},
                            "district_code": {"bsonType": ["string", "null"]},
                        },
                    },
                    "token_version": {"bsonType": ["int", "long"]},
                    "failed_login_attempts": {"bsonType": ["int", "long"]},
                },
            }
        },
        "applications": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["instrument_id", "owner_id", "status"],
                "properties": {
                    # Denormalized from the instrument at submission time
                    # (see routers/applications.py) so jurisdiction filtering
                    # is a plain indexed match, not a join on every query.
                    "state_code": {"bsonType": "string"},
                    "district_code": {"bsonType": "string"},
                    "status": {
                        "enum": [
                            "submitted",
                            "scheduled",
                            "inspected",
                            "certified",
                            "rejected",
                            "expiring",
                            "expired",
                        ]
                    }
                },
            }
        },
        "refresh_tokens": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["token_hash", "user_id", "expires_at", "revoked"],
            }
        },
    }

    for name, validator in validators.items():
        try:
            db.command("collMod", name, validator=validator, validationLevel="moderate")
        except OperationFailure:
            # Collection may not exist yet on a brand-new DB, or the
            # connected user may lack collMod privileges — either way,
            # app-layer (Pydantic) validation still applies, so this is a
            # defense-in-depth best-effort, not a hard requirement.
            pass
