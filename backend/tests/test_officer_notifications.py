"""Officers are emailed when an administrator changes their account:
jurisdiction, two-step reset, suspend, reactivate. Never blocks the action."""
import pytest
from passlib.context import CryptContext

from mfa_helpers import enroll_mfa, full_login

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
PASSWORD = "Old-Passw0rd!"


@pytest.fixture
def sent(client, monkeypatch):
    """Captures every outgoing mail; returns the list of (to, subject, body, html)."""
    import app.config.db as dbmod
    import app.routers.admin_users as admin_mod
    import app.services.mailer as mailer_mod

    mails = []
    monkeypatch.setattr(mailer_mod, "send_email", lambda to, subject, body, html=None, sender=None: mails.append((to, subject, body, html)) or True)
    monkeypatch.setattr(admin_mod, "smtp_is_configured", lambda: True)
    monkeypatch.setattr(admin_mod, "users_col", dbmod.db["users"])
    monkeypatch.setattr(admin_mod, "refresh_tokens_col", dbmod.db["refresh_tokens"])
    monkeypatch.setattr(admin_mod, "otp_verifications_col", dbmod.db["otp_verifications"])
    monkeypatch.setattr(admin_mod, "states_col", dbmod.db["states"])
    monkeypatch.setattr(admin_mod, "districts_col", dbmod.db["districts"])
    dbmod.db["states"].insert_one({"code": "WB", "name": "West Bengal"})
    dbmod.db["districts"].insert_many([
        {"code": "319", "state_code": "WB", "name": "Kolkata"},
        {"code": "320", "state_code": "WB", "name": "Murshidabad"},
    ])
    return mails


def _seed(role, email, mfa=False, **extra):
    import app.config.db as dbmod

    doc = {"name": f"Test {role}", "email": email, "password": _pwd.hash(PASSWORD), "role": role,
           "status": "active", "token_version": 0, **extra}
    doc["_id"] = dbmod.users_col.insert_one(doc).inserted_id
    creds = {"email": email, "password": PASSWORD, "_id": doc["_id"]}
    if mfa:
        creds["mfa_secret"] = enroll_mfa(doc["_id"])
    return creds


@pytest.fixture
def admin_h(client, sent):
    import app.config.db as dbmod

    dbmod.db["users"].create_index("email", unique=True)
    admin = _seed("admin", "boss@example.com", mfa=True)
    h = {"Authorization": f"Bearer {full_login(client, admin).json()['token']}"}
    sent.clear()  # login mails etc. are not what these tests are about
    return h


def test_changing_jurisdiction_emails_the_officer(client, admin_h, sent):
    officer = _seed("lmo", "lmo@example.com", jurisdiction={"state_code": "WB", "district_code": "319"})
    r = client.patch(f"/api/v1/admin/users/{officer['_id']}/jurisdiction", headers=admin_h,
                     json={"state_code": "WB", "district_code": "320"})
    assert r.status_code == 200
    assert len(sent) == 1
    to, subject, body, html = sent[0]
    assert to == "lmo@example.com" and "jurisdiction" in subject.lower()
    assert "Kolkata, West Bengal" in body and "Murshidabad, West Bengal" in body
    assert html and "Murshidabad" in html


def test_a_refused_jurisdiction_change_sends_nothing(client, admin_h, sent):
    officer = _seed("lmo", "lmo@example.com", jurisdiction={"state_code": "WB", "district_code": "319"})
    r = client.patch(f"/api/v1/admin/users/{officer['_id']}/jurisdiction", headers=admin_h, json={"state_code": "WB"})
    assert r.status_code == 400 and sent == []


def test_resetting_two_step_emails_the_officer(client, admin_h, sent):
    officer = _seed("gatc", "gatc@example.com", mfa=True)
    assert client.post(f"/api/v1/admin/users/{officer['_id']}/reset-mfa", headers=admin_h).status_code == 200
    assert len(sent) == 1 and sent[0][0] == "gatc@example.com" and "two-step" in sent[0][1].lower()


def test_suspending_emails_once_and_reactivating_emails_once(client, admin_h, sent):
    officer = _seed("lmo", "lmo@example.com")
    url = f"/api/v1/admin/users/{officer['_id']}"

    assert client.post(f"{url}/reject", headers=admin_h).status_code == 200
    assert len(sent) == 1 and "suspended" in sent[0][1].lower()
    assert client.post(f"{url}/reject", headers=admin_h).status_code == 200   # already suspended
    assert len(sent) == 1

    assert client.post(f"{url}/approve", headers=admin_h).status_code == 200
    assert len(sent) == 2 and "reactivated" in sent[1][1].lower() and sent[1][0] == "lmo@example.com"
    assert client.post(f"{url}/approve", headers=admin_h).status_code == 200  # already active
    assert len(sent) == 2


def test_officer_emails_never_contain_credentials(client, admin_h, sent):
    officer = _seed("lmo", "lmo@example.com", mfa=True)
    url = f"/api/v1/admin/users/{officer['_id']}"
    client.post(f"{url}/reset-mfa", headers=admin_h)
    client.post(f"{url}/reject", headers=admin_h)
    assert len(sent) == 2
    for _, _, body, html in sent:
        assert "temporary password" not in body.lower()
        assert "temporary password" not in html.lower()


def test_a_mail_failure_never_breaks_the_admin_action(client, admin_h, sent, monkeypatch):
    import app.services.mailer as mailer_mod

    def boom(*a, **k):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(mailer_mod, "send_email", boom)
    officer = _seed("lmo", "lmo@example.com")
    r = client.post(f"/api/v1/admin/users/{officer['_id']}/reject", headers=admin_h)
    assert r.status_code == 200 and r.json()["status"] == "rejected"


def test_no_mail_when_mail_is_not_configured(client, admin_h, sent, monkeypatch):
    import app.routers.admin_users as admin_mod

    monkeypatch.setattr(admin_mod, "smtp_is_configured", lambda: False)
    officer = _seed("lmo", "lmo@example.com")
    assert client.post(f"/api/v1/admin/users/{officer['_id']}/reject", headers=admin_h).status_code == 200
    assert sent == []


def test_officer_notice_job_raises_when_the_mail_was_not_sent(client, monkeypatch):
    import app.services.jobs as jobs

    monkeypatch.setattr(jobs, "send_officer_notice", lambda **kw: False)
    with pytest.raises(jobs.MailSendError):
        jobs.send_officer_notice_job(event="suspended", to="a@example.com", ctx={"name": "A"})
