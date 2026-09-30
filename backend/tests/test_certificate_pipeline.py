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
    # list_certificates() nudges the background reconciler; in tests that thread would
    # talk to the real (unpatched) Mongo client and hold the reconcile lock for ages.
    monkeypatch.setattr(certs, "start_reconcile", lambda *a, **k: False)

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


# ---- self-healing: certified applications with no certificate --------------

@pytest.fixture
def stranded(monkeypatch):
    """One owner with two certified applications: A has a certificate, B (the
    'beam scale') never got one because generation failed."""
    db = mongomock.MongoClient()["reconcile"]
    for name in ("applications_col", "certificates_col", "inspections_col"):
        monkeypatch.setattr(jobs, name, db[name.replace("_col", "")])
    monkeypatch.setattr(jobs, "broadcast_threadsafe", lambda *a, **k: None)
    monkeypatch.setattr(jobs, "_certificate_ready_message", lambda cert: None)
    monkeypatch.setattr(jobs, "_reconcile_lock", jobs.threading.Lock())
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    owner = ObjectId()
    ids = {}
    for label in ("A", "B"):
        app_id, insp_id = ObjectId(), ObjectId()
        ids[label] = (app_id, insp_id)
        db["applications"].insert_one(
            {"_id": app_id, "owner_id": owner, "instrument_id": ObjectId(), "status": "certified",
             "history": [{"from": "inspected", "to": "certified", "at": old.replace(tzinfo=None)}]}
        )
        db["inspections"].insert_one(
            {"_id": insp_id, "application_id": app_id, "result": "pass", "inspected_at": old.replace(tzinfo=None)}
        )
    db["certificates"].insert_one({"_id": "cert-A", "application_id": ids["A"][0]})
    return {"db": db, "owner": owner, "ids": ids}


def test_finds_only_certified_applications_without_a_certificate(stranded):
    missing = jobs.find_applications_missing_certificate(stranded["owner"])
    assert [a["_id"] for a in missing] == [stranded["ids"]["B"][0]]


def test_recently_certified_application_is_left_alone(stranded):
    # Its normal generation is probably still running -- don't race it.
    app_b = stranded["ids"]["B"][0]
    stranded["db"]["applications"].update_one(
        {"_id": app_b}, {"$set": {"history": [{"to": "certified", "at": datetime.now(timezone.utc)}]}}
    )
    assert jobs.find_applications_missing_certificate(stranded["owner"]) == []
    assert len(jobs.find_applications_missing_certificate(stranded["owner"], grace_seconds=0)) == 1


def test_reconcile_issues_the_missing_certificate(stranded, monkeypatch):
    issued = []

    def fake_issue(inspection_id):
        issued.append(inspection_id)
        cert = {"_id": "cert-B", "application_id": stranded["ids"]["B"][0]}
        stranded["db"]["certificates"].insert_one(dict(cert))
        return cert

    monkeypatch.setattr(jobs, "issue_certificate", fake_issue)
    result = jobs.reconcile_missing_certificates()
    assert result == {"issued": 1, "failed": 0, "skipped": False}
    assert issued == [stranded["ids"]["B"][1]]
    # Second run has nothing left to do.
    assert jobs.reconcile_missing_certificates()["issued"] == 0


def test_reconcile_records_failures_and_keeps_going(stranded, monkeypatch):
    def boom(inspection_id):
        raise RuntimeError("cloudinary exploded")

    monkeypatch.setattr(jobs, "issue_certificate", boom)
    assert jobs.reconcile_missing_certificates()["failed"] == 1
    app_b = stranded["db"]["applications"].find_one({"_id": stranded["ids"]["B"][0]})
    assert "cloudinary exploded" in app_b["certificate_error"]
    # ...and it is still reported as pending (failed=True) so the UI can say so.
    assert jobs.find_applications_missing_certificate(stranded["owner"])[0]["certificate_error"]
