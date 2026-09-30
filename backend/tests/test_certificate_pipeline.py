"""
Certificate pipeline: who can see which certificate, and that generation still
happens when Redis is configured but no RQ worker is running (the Render
web-service-only setup).
"""
from datetime import datetime, timedelta, timezone

import mongomock
import pytest
from bson import ObjectId
from fastapi import HTTPException

from app.routers import certificates as certs
from app.services import jobs


@pytest.fixture
def world(monkeypatch):
    db = mongomock.MongoClient()["certs"]
    monkeypatch.setattr(certs, "certificates_col", db["certificates"])
    monkeypatch.setattr(certs, "applications_col", db["applications"])
    monkeypatch.setattr(certs, "instruments_col", db["instruments"])
    monkeypatch.setattr(certs, "users_col", db["users"])
    monkeypatch.setattr(certs, "inspections_col", db["inspections"])
    monkeypatch.setattr(certs, "format_location", lambda loc: "Main Rd, Baharampur")

    now = datetime.now(timezone.utc)
    owner_a, owner_b = ObjectId(), ObjectId()
    out = {"db": db, "owner_a": owner_a, "owner_b": owner_b}

    def make(owner, district, cert_id, cert_no):
        inst_id, app_id = ObjectId(), ObjectId()
        db["instruments"].insert_one(
            {"_id": inst_id, "owner_id": owner, "type": "Platform Scale", "uiid": f"LM-{cert_no}",
             "manufacturer": "Acme", "model": "X1", "location": {}}
        )
        db["applications"].insert_one(
            {"_id": app_id, "owner_id": owner, "instrument_id": inst_id, "status": "certified",
             "state_code": "WB", "district_code": district}
        )
        db["certificates"].insert_one(
            {"_id": cert_id, "application_id": app_id, "instrument_id": inst_id, "cert_no": cert_no,
             "qr_url": "https://q", "pdf_url": "https://p.pdf", "issued_at": now.replace(tzinfo=None),
             "valid_until": (now + timedelta(days=365)).replace(tzinfo=None)}
        )

    make(owner_a, "319", "cert-a", "CERT-A")
    make(owner_b, "320", "cert-b", "CERT-B")
    return out


def _ids(result):
    return sorted(c["id"] for c in result)


def test_owner_only_sees_own_certificates(world):
    assert _ids(certs.list_certificates(user={"_id": world["owner_a"], "role": "owner"})) == ["cert-a"]
    assert _ids(certs.list_certificates(user={"_id": world["owner_b"], "role": "owner"})) == ["cert-b"]


def test_owner_cannot_fetch_someone_elses_certificate(world):
    with pytest.raises(HTTPException) as exc:
        certs.get_certificate("cert-b", user={"_id": world["owner_a"], "role": "owner"})
    assert exc.value.status_code == 404


def test_admin_sees_everything(world):
    assert _ids(certs.list_certificates(user={"_id": ObjectId(), "role": "admin"})) == ["cert-a", "cert-b"]


def test_officer_is_scoped_to_jurisdiction_and_fails_closed(world):
    district_officer = {"_id": ObjectId(), "role": "lmo", "jurisdiction": {"state_code": "WB", "district_code": "319"}}
    state_officer = {"_id": ObjectId(), "role": "gatc", "jurisdiction": {"state_code": "WB", "district_code": None}}
    no_jurisdiction = {"_id": ObjectId(), "role": "lmo"}
    assert _ids(certs.list_certificates(user=district_officer)) == ["cert-a"]
    assert _ids(certs.list_certificates(user=state_officer)) == ["cert-a", "cert-b"]
    assert certs.list_certificates(user=no_jurisdiction) == []


def test_serialized_certificate_has_number_instrument_and_utc_dates(world):
    cert = certs.get_certificate("cert-a", user={"_id": world["owner_a"], "role": "owner"})
    assert cert["cert_no"] == "CERT-A"
    assert cert["instrument"]["uiid"] == "LM-CERT-A"
    assert cert["instrument"]["location"] == "Main Rd, Baharampur"
    assert cert["verified_on"].endswith("+00:00") and cert["valid_until"].endswith("+00:00")
    assert cert["is_expired"] is False


# ---- generation dispatch -------------------------------------------------

class _FakeThread:
    started = []

    def __init__(self, target=None, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        _FakeThread.started.append(self.args)


class _FakeQueue:
    def __init__(self):
        self.enqueued = []

    def enqueue(self, fn, *args):
        self.enqueued.append((fn, args))


@pytest.fixture
def dispatch(monkeypatch):
    _FakeThread.started = []
    monkeypatch.setattr(jobs.threading, "Thread", _FakeThread)
    return _FakeThread


def test_no_redis_generates_in_a_thread(monkeypatch, dispatch):
    monkeypatch.setattr(jobs, "get_queue", lambda: None)
    jobs.start_certificate_generation("insp-1")
    assert dispatch.started == [("insp-1",)]


def test_redis_without_a_worker_does_not_strand_the_job(monkeypatch, dispatch):
    queue = _FakeQueue()
    monkeypatch.setattr(jobs, "get_queue", lambda: queue)
    monkeypatch.setattr(jobs, "_worker_available", lambda q: False)
    jobs.start_certificate_generation("insp-2")
    assert queue.enqueued == []
    assert dispatch.started == [("insp-2",)]


def test_redis_with_a_worker_uses_the_queue(monkeypatch, dispatch):
    queue = _FakeQueue()
    monkeypatch.setattr(jobs, "get_queue", lambda: queue)
    monkeypatch.setattr(jobs, "_worker_available", lambda q: True)
    jobs.start_certificate_generation("insp-3")
    assert queue.enqueued == [(jobs.generate_certificate_job, ("insp-3",))]
    assert dispatch.started == []
