from pymongo import MongoClient
from pymongo.errors import OperationFailure
from app.config.settings import MONGO_URI, DB_NAME
from app.models.instrument import ALLOWED_INSTRUMENT_TYPES
from app.utils.validators import MAX_SHORT_TEXT, MAX_LONG_TEXT, MAX_CODE_LENGTH

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
# One doc per owner status email, _id = dedupe key (e.g. "certificate_issued:<id>").
# Claimed before sending so the same mail is never sent twice; see
# app/services/owner_notifications.py.
email_log_col = db["email_log"]
# Refresh tokens live in their own collection so they can be listed/revoked
# per-user (e.g. "log out of all devices") without touching users_col at all.
refresh_tokens_col = db["refresh_tokens"]
# OTP codes for email/phone verification — one doc per (identifier, purpose)
# pair, hashed code + expiry + attempt count. TTL index below cleans up
# abandoned codes; verify_otp()/consume_verification_proof() in
# app/services/otp.py manage success/expiry/consumption during normal use.
otp_verifications_col = db["otp_verifications"]
# Append-only security audit trail (password resets/changes etc.) — see
# app/services/audit.py. Never read or modified by the API itself.
audit_logs_col = db["audit_logs"]

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
    # One certificate per application, enforced by the DB so a retried job and the
    # reconciler can never double-issue. Isolated in its own try: if legacy
    # duplicates already exist this can't be built, and that must not abort the
    # rest of startup (the scheduler starts right after this function).
    try:
        certificates_col.create_index("application_id", unique=True)
    except Exception:
        import logging
        logging.getLogger("maapsetu").warning(
            "Could not create the unique index on certificates.application_id "
            "(duplicate certificates for one application already exist?).", exc_info=True,
        )

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

    # OTP lookups are always by (identifier, purpose) — unique so a new
    # send overwrites (upserts) any still-pending code for the same
    # identifier+purpose rather than accumulating stale ones. TTL index is
    # a backstop for codes nobody came back to verify or consume.
    otp_verifications_col.create_index([("identifier", 1), ("purpose", 1)], unique=True)
    otp_verifications_col.create_index("expires_at", expireAfterSeconds=0)

    # Audit log: keep for AUDIT_LOG_RETENTION_DAYS (default 365; CERT-In asks
    # for at least 180 days), then let Mongo expire it. Wrapped so that a
    # changed retention value (which makes Mongo reject re-creating an
    # existing index with different options) can never stop startup.
    try:
        from app.config.settings import AUDIT_LOG_RETENTION_DAYS

        audit_logs_col.create_index("created_at", expireAfterSeconds=AUDIT_LOG_RETENTION_DAYS * 86400)
        audit_logs_col.create_index([("event", 1), ("created_at", -1)])
        audit_logs_col.create_index([("email", 1), ("created_at", -1)])
    except Exception:  # pragma: no cover - best effort
        pass

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
    # Bounds/patterns mirrored from app/utils/validators.py (MAX_SHORT_TEXT,
    # MAX_LONG_TEXT, MAX_CODE_LENGTH, PHONE_REGEX) so this DB-level backstop
    # actually matches what the Pydantic models enforce, rather than being
    # looser than the API boundary it's meant to back up. Kept as literal
    # values here (not importing PHONE_REGEX.pattern directly) since Mongo's
    # $jsonSchema pattern uses PCRE-ish syntax via a plain string, not a
    # compiled Python regex object.
    PHONE_PATTERN = "^[6-9]\\d{9}$"
    LOCATION_SCHEMA = {
        "bsonType": "object",
        "required": ["state_code", "district_code", "address_line"],
        "properties": {
            "state_code": {"bsonType": "string", "maxLength": MAX_CODE_LENGTH},
            "district_code": {"bsonType": "string", "maxLength": MAX_CODE_LENGTH},
            "address_line": {"bsonType": "string", "maxLength": MAX_LONG_TEXT},
        },
    }

    validators = {
        "users": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["name", "email", "password", "role", "status"],
                "properties": {
                    "name": {"bsonType": "string", "maxLength": MAX_SHORT_TEXT},
                    "email": {"bsonType": "string"},
                    "password": {"bsonType": "string"},
                    "role": {"enum": ["owner", "lmo", "gatc", "admin"]},
                    "status": {"enum": ["pending", "active", "rejected"]},
                    "org_name": {"bsonType": ["string", "null"], "maxLength": MAX_LONG_TEXT},
                    # contact is optional (validate_phone treats "" the same
                    # as not provided, normalized to None) — so null/absent
                    # must stay allowed here too, only a non-null value gets
                    # pattern-checked.
                    "contact": {"bsonType": ["string", "null"], "pattern": PHONE_PATTERN},
                    # jurisdiction.district_code is intentionally not
                    # required here — omitted means state-level scope
                    # (GATC); Pydantic (OfficerCreate) is what actually
                    # enforces state_code being present for lmo/gatc.
                    "jurisdiction": {
                        "bsonType": ["object", "null"],
                        "properties": {
                            "state_code": {"bsonType": "string", "maxLength": MAX_CODE_LENGTH},
                            "district_code": {"bsonType": ["string", "null"], "maxLength": MAX_CODE_LENGTH},
                        },
                    },
                    "token_version": {"bsonType": ["int", "long"]},
                    "failed_login_attempts": {"bsonType": ["int", "long"]},
                },
            }
        },
        # Single source of truth for this collection's validator — this
        # used to exist as two separate "instruments" entries in this same
        # dict (a merge-conflict artifact), which Python dict literals
        # silently resolve by keeping only the last one, discarding the
        # other's rules with no error or warning. Consolidated back into
        # one entry here, keeping the stricter maxLength/LOCATION_SCHEMA
        # bounds from the original version, plus explicit uiid typing
        # from the other. `type`'s enum is deliberately sourced from
        # ALLOWED_INSTRUMENT_TYPES (imported above), not a second
        # hardcoded list here — this collection previously had a stale,
        # independently-drifted validator (mismatched casing, e.g.
        # "LoadCell" vs. "Load Cell") that nothing was keeping in sync;
        # deriving it from the model's own list means collMod below always
        # re-asserts a validator that matches app/models/instrument.py.
        "instruments": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["owner_id", "uiid", "type", "manufacturer", "model", "capacity", "serial_no", "location"],
                "properties": {
                    "type": {"enum": ALLOWED_INSTRUMENT_TYPES},
                    "uiid": {"bsonType": "string"},
                    "manufacturer": {"bsonType": "string", "maxLength": MAX_SHORT_TEXT},
                    "model": {"bsonType": "string", "maxLength": MAX_SHORT_TEXT},
                    # No maxLength/pattern tied to CAPACITY_NUMBER_REGEX here
                    # on purpose: what's actually stored is the number *plus*
                    # its unit (e.g. "30 kg"), appended server-side in
                    # routers/instruments.py — the bare-number check only
                    # applies to what the client submits, not what's stored.
                    "capacity": {"bsonType": "string"},
                    "serial_no": {"bsonType": "string", "maxLength": MAX_SHORT_TEXT},
                    "location": LOCATION_SCHEMA,
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
                    "state_code": {"bsonType": "string", "maxLength": MAX_CODE_LENGTH},
                    "district_code": {"bsonType": "string", "maxLength": MAX_CODE_LENGTH},
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
        "otp_verifications": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["identifier", "purpose", "code_hash", "expires_at", "attempts"],
                "properties": {
                    "purpose": {"enum": ["email_verify", "password_reset"]},
                    "attempts": {"bsonType": ["int", "long"]},
                },
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