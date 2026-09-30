"""
Owner status-update emails: templates, de-duplication, retry-after-failure,
expiry milestones and the cron wiring. Runs on mongomock, no SMTP, no Redis.
"""
from datetime import datetime, timedelta, timezone

import mongomock
import pytest
from bson import ObjectId

from app.services import email_templates, expiry_cron
from app.services import owner_notifications as on


@pytest.fixture
def env(monkeypatch):
    db = mongomock.MongoClient()["t"]
    sent = []

    def fake_send(to, subject, body, html=None):
        sent.append({"to": to, "subject": subject, "body": body, "html": html})
        return True

    owner_id = ObjectId()
    db["users"].insert_one({"_id": owner_id, "name": "Asha", "email": "asha@example.com", "role": "owner"})
    instrument = {
        "_id": ObjectId(), "owner_id": owner_id, "uiid": "LM-000001",
        "type": "Platform Scale", "manufacturer": "Acme <b>", "model": "X1",
        "serial_no": "SN1", "location": {"state_code": "WB", "district_code": "1", "address_line": "Main Rd"},
    }
    db["instruments"].insert_one(instrument)

    monkeypatch.setattr(on, "email_log_col", db["email_log"])
    monkeypatch.setattr(on, "users_col", db["users"])
    monkeypatch.setattr(on, "_load_instrument", lambda iid: db["instruments"].find_one({"_id": iid}))
    monkeypatch.setattr(on, "format_location", lambda loc: "Main Rd, Kolkata, West Bengal")
    monkeypatch.setattr(on.mailer, "is_configured", lambda: True)
    monkeypatch.setattr(on.mailer, "send_email", fake_send)
    # Run "background" sends synchronously so tests can assert on them.
    monkeypatch.setattr(on, "_dispatch", lambda *a, inline=False: on._run_quietly(*a))
    return {"db": db, "sent": sent, "owner_id": owner_id, "instrument": instrument, "send": fake_send}


def test_templates_escape_user_input_and_render_every_event():
    ctx = {
        "owner_name": "A<script>", "apply_url": "u", "application_id": "1", "application_url": "u",
        "reapply_url": "u", "cert_no": "C1", "verify_url": "v", "certificate_url": "c", "renew_url": "r",
        "days_left": 7, "valid_until": datetime(2027, 1, 1), "observations": "<img src=x>",
        "instrument": {"type": "Platform Scale", "uiid": "LM-1", "manufacturer": "<b>Acme</b>", "model": "M", "serial_no": "S"},
    }
    for event in email_templates._BUILDERS:
        subject, text, html = email_templates.render(event, ctx)
        assert subject and text and html
        assert "<script>" not in html and "<b>Acme</b>" not in html and "<img src=x>" not in html
        assert "\n" not in subject


def test_registered_email_goes_to_owner_with_html_and_text(env):
    on.notify_instrument_registered(env["instrument"])
    assert len(env["sent"]) == 1
    mail = env["sent"][0]
    assert mail["to"] == "asha@example.com"
    assert "LM-000001" in mail["subject"]
    assert mail["html"] and "Acme &lt;b&gt;" in mail["html"]


def test_same_event_is_never_sent_twice(env):
    on.notify_instrument_registered(env["instrument"])
    on.notify_instrument_registered(env["instrument"])
    assert len(env["sent"]) == 1
    assert env["db"]["email_log"].find_one({"_id": f"instrument_registered:{env['instrument']['_id']}"})["status"] == "sent"


def test_failed_send_releases_claim_so_retry_succeeds(env, monkeypatch):
    monkeypatch.setattr(on.mailer, "send_email", lambda *a, **k: False)
    with pytest.raises(on.EmailDeliveryError):
        on.send_owner_email_job("k1", "a@b.c", "s", "t", "h")
    assert env["db"]["email_log"].count_documents({}) == 0
    monkeypatch.setattr(on.mailer, "send_email", env["send"])
    assert on.send_owner_email_job("k1", "a@b.c", "s", "t", "h") is True


def test_stale_sending_claim_is_taken_over(env):
    old = datetime.now(timezone.utc) - timedelta(minutes=30)
    env["db"]["email_log"].insert_one({"_id": "k2", "status": "sending", "created_at": old})
    assert on.send_owner_email_job("k2", "a@b.c", "s", "t", "h") is True


def test_nothing_happens_when_smtp_not_configured(env, monkeypatch):
    monkeypatch.setattr(on.mailer, "is_configured", lambda: False)
    on.notify_instrument_registered(env["instrument"])
    assert env["sent"] == [] and env["db"]["email_log"].count_documents({}) == 0


def test_notify_never_raises(env, monkeypatch):
    monkeypatch.setattr(on, "_get_owner", lambda _id: (_ for _ in ()).throw(RuntimeError("db down")))
    on.notify_instrument_registered(env["instrument"])  # must not raise


def test_inspection_pass_and_fail_use_different_mails(env):
    app = {"_id": ObjectId(), "instrument_id": env["instrument"]["_id"], "owner_id": env["owner_id"]}
    on.notify_inspection_result(app, {"result": "pass", "inspected_at": datetime.now(timezone.utc)})
    app2 = {**app, "_id": ObjectId()}
    on.notify_inspection_result(app2, {"result": "fail", "observations": "Seal broken", "inspected_at": datetime.now(timezone.utc)})
    assert "passed" in env["sent"][0]["subject"]
    assert "did not pass" in env["sent"][1]["subject"] and "Seal broken" in env["sent"][1]["body"]


@pytest.mark.parametrize("days,expected", [(45, None), (30, 30), (20, 30), (15, 15), (10, 15), (5, 7), (1, 1), (0, 1)])
def test_reminder_milestones(days, expected):
    assert on.pick_reminder_milestone(days) == expected


def test_expiry_reminder_sent_once_per_milestone(env):
    now = datetime.now(timezone.utc)
    cert = {"_id": "c1", "cert_no": "CERT-1", "instrument_id": env["instrument"]["_id"],
            "valid_until": (now + timedelta(days=20)).replace(tzinfo=None)}  # naive, as Mongo returns it
    on.notify_expiry_reminder(cert, now=now)
    on.notify_expiry_reminder(cert, now=now + timedelta(hours=1))
    assert len(env["sent"]) == 1
    # 5 days later the 7-day milestone is a new mail
    on.notify_expiry_reminder(cert, now=now + timedelta(days=15))
    assert len(env["sent"]) == 2


def test_cron_emails_expiring_but_not_renewed_certificates(env, monkeypatch):
    db = env["db"]
    now = datetime.now(timezone.utc)
    iid = env["instrument"]["_id"]
    db["certificates"].insert_many([
        {"_id": "old", "cert_no": "C-OLD", "instrument_id": iid, "application_id": ObjectId(), "valid_until": now + timedelta(days=10)},
    ])
    monkeypatch.setattr(expiry_cron, "certificates_col", db["certificates"])
    monkeypatch.setattr(expiry_cron, "alerts_col", db["alerts"])
    monkeypatch.setattr(expiry_cron, "_acquire_run_lock", lambda name: True)
    monkeypatch.setattr(expiry_cron, "mark_expiring", lambda app_id: None)

    expiry_cron.check_expiring_certificates()
    assert len(env["sent"]) == 1 and "expires in" in env["sent"][0]["subject"]

    # Owner renews: a newer cert exists -> no further reminders for the old one.
    db["email_log"].delete_many({})
    db["certificates"].insert_one({"_id": "new", "cert_no": "C-NEW", "instrument_id": iid, "application_id": ObjectId(), "valid_until": now + timedelta(days=365)})
    expiry_cron.check_expiring_certificates()
    assert len(env["sent"]) == 1


def test_cron_expired_notice_only_for_recent_expiry(env, monkeypatch):
    db = env["db"]
    now = datetime.now(timezone.utc)
    iid = env["instrument"]["_id"]
    db["certificates"].insert_many([
        {"_id": "recent", "cert_no": "C-R", "instrument_id": iid, "application_id": ObjectId(), "valid_until": now - timedelta(days=1)},
    ])
    other = ObjectId()
    db["instruments"].insert_one({**env["instrument"], "_id": other, "serial_no": "SN2"})
    db["certificates"].insert_one({"_id": "ancient", "cert_no": "C-A", "instrument_id": other, "application_id": ObjectId(), "valid_until": now - timedelta(days=200)})
    monkeypatch.setattr(expiry_cron, "certificates_col", db["certificates"])
    monkeypatch.setattr(expiry_cron, "alerts_col", db["alerts"])
    monkeypatch.setattr(expiry_cron, "_acquire_run_lock", lambda name: True)
    monkeypatch.setattr(expiry_cron, "mark_expired", lambda app_id: None)

    expiry_cron.check_expired_certificates()
    assert len(env["sent"]) == 1
    assert "expired" in env["sent"][0]["subject"].lower() and "C-R" in env["sent"][0]["body"]
