"""
OTP send/verify rate limits, owner-email retry backoff, MongoDB read-replica
routing, and the Redis-backed rate limiter.
"""
import os
import pathlib
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_DIR / "app"


def _audit(event=None):
    import app.config.db as dbmod

    return list(dbmod.db["audit_logs"].find({"event": event} if event else {}))


@pytest.fixture
def otp_env(client, monkeypatch):
    """Wires the OTP router + service to the in-memory DB and captures emails."""
    import app.config.db as dbmod
    import app.routers.otp as otp_router
    import app.services.otp as otp_mod

    monkeypatch.setattr(otp_mod, "otp_verifications_col", dbmod.db["otp_verifications"])
    monkeypatch.setattr(otp_router, "users_col", dbmod.db["users"])
    sent: list[dict] = []
    monkeypatch.setattr(otp_router, "send_email", lambda to, subject, body, html=None, sender=None: sent.append({"to": to, "body": body}) or True)
    return sent


# ============================================================ OTP /send


def test_otp_send_emails_a_code(client, otp_env):
    r = client.post("/api/v1/otp/send", json={"channel": "email", "identifier": "New.User@Example.com"})
    assert r.status_code == 200 and r.json() == {"sent": True}
    assert len(otp_env) == 1 and otp_env[0]["to"] == "new.user@example.com"
    ev = _audit("signup_otp_requested")[-1]
    assert (ev["outcome"], ev["detail"], ev["email"]) == ("success", "code_sent", "new.user@example.com")


def test_otp_send_has_a_per_address_cooldown(client, otp_env):
    body = {"channel": "email", "identifier": "victim@example.com"}
    assert client.post("/api/v1/otp/send", json=body).status_code == 200
    again = client.post("/api/v1/otp/send", json=body)
    assert again.status_code == 429
    assert "wait" in again.json()["detail"].lower() and again.headers["retry-after"] == "60"
    assert len(otp_env) == 1                       # no second email went out
    assert _audit("signup_otp_requested")[-1]["detail"] == "cooldown"

    # a different address is unaffected, and so is the same address once the cooldown has passed
    assert client.post("/api/v1/otp/send", json={"channel": "email", "identifier": "other@example.com"}).status_code == 200
    import app.config.db as dbmod

    dbmod.db["otp_verifications"].update_one(
        {"identifier": "victim@example.com"}, {"$set": {"created_at": datetime.now(timezone.utc) - timedelta(seconds=61)}}
    )
    assert client.post("/api/v1/otp/send", json=body).status_code == 200


def test_cooldown_answer_is_the_same_for_every_address(client, otp_env):
    """Must not reveal whether an address has an account."""
    import app.config.db as dbmod

    dbmod.db["users"].insert_one({"email": "exists@example.com", "role": "owner", "password": "x", "status": "active"})
    answers = []
    for addr in ("exists@example.com", "ghost@example.com"):
        first = client.post("/api/v1/otp/send", json={"channel": "email", "identifier": addr})
        second = client.post("/api/v1/otp/send", json={"channel": "email", "identifier": addr})
        answers.append((first.status_code, first.json(), second.status_code, second.json()["detail"]))
    assert answers[0] == answers[1]


def test_otp_send_has_a_per_ip_limit(client, otp_env):
    codes = [
        client.post("/api/v1/otp/send", json={"channel": "email", "identifier": f"user{i}@example.com"}).status_code
        for i in range(7)
    ]
    assert codes[:5] == [200] * 5
    assert codes[5:] == [429, 429]
    assert len(otp_env) == 5


def test_otp_verify_is_rate_limited_too(client, otp_env):
    statuses = [
        client.post("/api/v1/otp/verify", json={"channel": "email", "identifier": "a@example.com", "code": "000000"}).status_code
        for _ in range(17)
    ]
    assert statuses[:15] == [400] * 15
    assert statuses[15:] == [429, 429]


def test_otp_send_does_not_wait_for_the_mail_server(client, otp_env, monkeypatch):
    """A slow/broken SMTP server must not make the request slow or fail."""
    import app.routers.otp as otp_router

    attempts = []

    def boom(**_k):
        attempts.append(1)
        raise RuntimeError("smtp down")

    monkeypatch.setattr(otp_router, "send_email", boom)
    # raise_server_exceptions=False: the failure happens AFTER the response has been
    # sent (in the background task), exactly as it would under uvicorn.
    from fastapi.testclient import TestClient

    from app.main import app

    lenient = TestClient(app, raise_server_exceptions=False)
    r = lenient.post("/api/v1/otp/send", json={"channel": "email", "identifier": "x@example.com"})
    assert r.status_code == 200 and r.json() == {"sent": True}
    assert attempts == [1]   # the broken mail function really was called


# ================================================== email retry backoff


def test_owner_emails_retry_with_increasing_delays(monkeypatch):
    import rq

    import app.services.owner_notifications as notif

    class FakeQueue:
        calls: list = []

        def enqueue(self, fn, *args, **kwargs):
            self.calls.append((fn, args, kwargs))

    queue = FakeQueue()
    monkeypatch.setattr(notif, "_get_queue", lambda: queue)
    monkeypatch.setattr(notif, "EMAIL_USE_QUEUE", True)
    monkeypatch.setattr(rq.Worker, "count", classmethod(lambda cls, *a, **k: 1))

    notif._dispatch("key-1", "owner@example.com", "subj", "text", "<p>html</p>")

    assert len(queue.calls) == 1
    retry = queue.calls[0][2]["retry"]
    assert retry.max == 3 and retry.intervals == [10, 60, 300]
    assert notif.EMAIL_RETRY_INTERVALS == [10, 60, 300]


# ========================================================= read replicas


def test_read_replica_is_a_no_op_by_default():
    import app.config.db as dbmod

    col = dbmod.db["anything"]
    assert dbmod.read_replica(col) is col


@pytest.mark.parametrize("preference,expected", [
    ("secondaryPreferred", "SecondaryPreferred"),
    ("nearest", "Nearest"),
    ("primaryPreferred", "PrimaryPreferred"),
])
def test_read_replica_applies_the_configured_preference(monkeypatch, preference, expected):
    from pymongo import MongoClient

    import app.config.db as dbmod

    monkeypatch.setattr(dbmod, "MONGO_READ_PREFERENCE", preference)
    real = MongoClient("mongodb://localhost:1", connect=False)["x"]["y"]   # never actually connects
    routed = dbmod.read_replica(real)
    assert routed.read_preference.name == expected and routed.full_name == real.full_name
    assert real.read_preference.name == "Primary"                          # the original is untouched


def _settings_import(env_value):
    env = {**os.environ, "MONGO_READ_PREFERENCE": env_value}
    return subprocess.run(
        [sys.executable, "-c", "import app.config.settings as s; print(s.MONGO_READ_PREFERENCE)"],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True,
    )


def test_read_preference_setting_is_validated_at_startup():
    ok = _settings_import("secondaryPreferred")
    assert ok.returncode == 0 and ok.stdout.strip() == "secondaryPreferred"
    for bad in ("secondary", "bogus"):
        res = _settings_import(bad)
        assert res.returncode != 0 and "MONGO_READ_PREFERENCE" in res.stderr


def test_replica_reads_are_used_only_where_staleness_is_harmless():
    """Security-critical code must NEVER read from a replica (a revoked token or
    a suspended account has to take effect immediately)."""
    users_of_helper = {
        str(path.relative_to(APP_DIR)).replace("\\", "/")
        for path in APP_DIR.rglob("*.py")
        if "read_replica(" in path.read_text(encoding="utf-8")
    }
    assert users_of_helper == {
        "config/db.py",            # the helper itself
        "routers/geo.py",          # reference data
        "routers/dashboard.py",    # aggregate counts
        "routers/certificates.py", # public certificate verification
        "routers/admin_audit.py",  # audit-log viewer
    }
    # ...and within certificates.py only the public verify endpoint uses it.
    src = (APP_DIR / "routers" / "certificates.py").read_text(encoding="utf-8")
    verify_start, verify_end = src.index('@router.get("/verify/{cert_id}")'), src.index('@router.get("/pending")')
    outside = src[:verify_start] + src[verify_end:]
    assert "read_replica(" not in outside.replace("import read_replica", "").replace(", read_replica", "")


@pytest.mark.parametrize("path", ["/api/v1/geo/states"])
def test_geo_reads_go_through_the_replica_helper(client, monkeypatch, path):
    import app.routers.geo as geo_mod

    asked = []
    monkeypatch.setattr(geo_mod, "read_replica", lambda col: asked.append(col.name) or col)
    monkeypatch.setattr(geo_mod, "states_col", __import__("app.config.db", fromlist=["db"]).db["states"])
    assert client.get(path).status_code == 200
    assert asked == ["states"]


# ================================================ Redis-backed rate limiter


def test_rate_limiter_uses_redis_when_configured_and_memory_otherwise():
    code = "from app.rate_limit import limiter as l; print(l._storage_uri, l._in_memory_fallback_enabled)"
    base = {**os.environ, "REDIS_URL": ""}
    no_redis = subprocess.run([sys.executable, "-c", code], cwd=BACKEND_DIR, env=base, capture_output=True, text=True)
    with_redis = subprocess.run([sys.executable, "-c", code], cwd=BACKEND_DIR, capture_output=True, text=True,
                                env={**base, "REDIS_URL": "redis://localhost:6379/0"})
    assert no_redis.stdout.split()[-2:] == ["memory://", "False"]
    assert with_redis.stdout.split()[-2:] == ["redis://localhost:6379/0", "True"]   # falls back to memory if Redis is down


def test_rate_limiter_keeps_enforcing_when_redis_is_unreachable():
    """A Redis outage must degrade the limiter to per-process memory, not turn
    every rate-limited request (including sign-in) into an error."""
    script = """
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.rate_limit import limiter
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
@app.get("/ping")
@limiter.limit("3/minute")
def ping(request: Request):
    return {"ok": True}
c = TestClient(app, raise_server_exceptions=False)
print([c.get("/ping").status_code for _ in range(5)])
"""
    res = subprocess.run([sys.executable, "-c", script], cwd=BACKEND_DIR, capture_output=True, text=True, timeout=120,
                         env={**os.environ, "REDIS_URL": "redis://127.0.0.1:1/0"})
    assert res.stdout.strip().splitlines()[-1] == "[200, 200, 200, 429, 429]", res.stdout + res.stderr


# ---------------------------------------------------------- OTP mail format


def test_otp_mails_are_noreply_and_carry_the_code():
    import re

    from app.services.email_templates import render_otp

    for purpose in ("signup", "password_reset"):
        subject, text, html = render_otp(purpose, "482913", 10)
        assert "MaapSetu" in subject
        assert re.findall(r"\b\d{6}\b", text) == ["482913"]
        assert "482913" in html and "10 minutes" in text
        assert "do not reply" in text.lower() and "do not reply" in html.lower()
        assert "Do not share this OTP" in text


def test_noreply_sender_falls_back_to_smtp_from_address(monkeypatch):
    import app.services.mailer as mailer_mod

    monkeypatch.setattr(mailer_mod, "NOREPLY_FROM", "")
    monkeypatch.setattr(mailer_mod, "SMTP_FROM", "MaapSetu <alerts@example.gov.in>")
    from email.utils import parseaddr

    assert parseaddr(mailer_mod.noreply_sender()) == ("MaapSetu (No-Reply)", "alerts@example.gov.in")
    monkeypatch.setattr(mailer_mod, "NOREPLY_FROM", "MaapSetu <noreply@example.gov.in>")
    assert mailer_mod.noreply_sender() == "MaapSetu <noreply@example.gov.in>"
