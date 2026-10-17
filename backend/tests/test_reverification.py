"""Re-verification: application type, link to the previous certificate, one open application per instrument."""
from datetime import datetime, timedelta, timezone

import mongomock
import pytest
from bson import ObjectId
from fastapi import HTTPException

import app.routers.applications as apps
import app.routers.certificates as certs
from app.models.application import ApplicationCreate


@pytest.fixture
def world(monkeypatch):
    db = mongomock.MongoClient()["reverify"]
    for mod in (apps,):
        monkeypatch.setattr(mod, "applications_col", db["applications"])
        monkeypatch.setattr(mod, "certificates_col", db["certificates"])
        monkeypatch.setattr(mod, "instruments_col", db["instruments"])
    monkeypatch.setattr(apps, "notify_application_submitted", lambda doc: None)
    monkeypatch.setattr(apps, "broadcast_threadsafe", lambda *a, **k: None)

    owner = {"_id": ObjectId(), "role": "owner"}
    other = {"_id": ObjectId(), "role": "owner"}
    loc = {"state_code": "WB", "district_code": "319"}
    inst = db["instruments"].insert_one({"owner_id": owner["_id"], "location": loc, "uiid": "LM-1"}).inserted_id
    inst2 = db["instruments"].insert_one({"owner_id": owner["_id"], "location": loc, "uiid": "LM-2"}).inserted_id
    return {"db": db, "owner": owner, "other": other, "inst": inst, "inst2": inst2}


def _cert(db, inst, cert_id, cert_no, days_left):
    now = datetime.now(timezone.utc)
    db["certificates"].insert_one({
        "_id": cert_id, "instrument_id": inst, "application_id": ObjectId(), "cert_no": cert_no,
        "issued_at": now - timedelta(days=365 - days_left), "valid_until": now + timedelta(days=days_left),
    })


def test_first_application_is_initial(world):
    out = apps.submit_application(ApplicationCreate(instrument_id=str(world["inst"])), current_user=world["owner"])
    assert out.application_type == "initial"
    assert out.previous_certificate_id is None and out.previous_cert_no is None


def test_instrument_with_certificate_is_a_renewal_linked_to_the_newest_one(world):
    _cert(world["db"], world["inst"], "old", "CERT-OLD", -400)
    _cert(world["db"], world["inst"], "new", "CERT-NEW", -10)
    out = apps.submit_application(ApplicationCreate(instrument_id=str(world["inst"])), current_user=world["owner"])
    assert out.application_type == "renewal"
    assert (out.previous_certificate_id, out.previous_cert_no) == ("new", "CERT-NEW")
    stored = world["db"]["applications"].find_one({"_id": ObjectId(out.id)})
    assert stored["application_type"] == "renewal" and stored["previous_certificate_id"] == "new"


def test_explicit_previous_certificate_is_used(world):
    _cert(world["db"], world["inst"], "old", "CERT-OLD", -400)
    _cert(world["db"], world["inst"], "new", "CERT-NEW", -10)
    out = apps.submit_application(
        ApplicationCreate(instrument_id=str(world["inst"]), previous_certificate_id="old"), current_user=world["owner"]
    )
    assert out.previous_certificate_id == "old"


def test_certificate_of_another_instrument_is_rejected(world):
    _cert(world["db"], world["inst2"], "other-inst", "CERT-X", -10)
    with pytest.raises(HTTPException) as exc:
        apps.submit_application(
            ApplicationCreate(instrument_id=str(world["inst"]), previous_certificate_id="other-inst"),
            current_user=world["owner"],
        )
    assert exc.value.status_code == 422
    assert world["db"]["applications"].count_documents({}) == 0


def test_unknown_certificate_id_is_rejected_even_without_any_certificate(world):
    with pytest.raises(HTTPException) as exc:
        apps.submit_application(
            ApplicationCreate(instrument_id=str(world["inst"]), previous_certificate_id="nope"), current_user=world["owner"]
        )
    assert exc.value.status_code == 422


def test_cannot_renew_before_the_window_opens(world):
    _cert(world["db"], world["inst"], "live", "CERT-LIVE", 100)
    with pytest.raises(HTTPException) as exc:
        apps.submit_application(ApplicationCreate(instrument_id=str(world["inst"])), current_user=world["owner"])
    assert exc.value.status_code == 409 and "from " in exc.value.detail
    assert world["db"]["applications"].count_documents({}) == 0


def test_can_renew_inside_the_window_and_expiry_is_recorded(world):
    _cert(world["db"], world["inst"], "soon", "CERT-SOON", 5)
    out = apps.submit_application(ApplicationCreate(instrument_id=str(world["inst"])), current_user=world["owner"])
    assert out.application_type == "renewal" and out.previous_cert_no == "CERT-SOON"
    assert out.previous_valid_until is not None and out.previous_valid_until > datetime.now(timezone.utc)


def test_window_edges(world, monkeypatch):
    monkeypatch.setattr(apps, "REVERIFY_WINDOW_DAYS", 30)
    _cert(world["db"], world["inst"], "edge", "CERT-EDGE", 31)
    with pytest.raises(HTTPException):
        apps.submit_application(ApplicationCreate(instrument_id=str(world["inst"])), current_user=world["owner"])
    world["db"]["certificates"].delete_many({})
    _cert(world["db"], world["inst"], "edge2", "CERT-EDGE2", 29)
    apps.submit_application(ApplicationCreate(instrument_id=str(world["inst"])), current_user=world["owner"])


def test_window_of_zero_means_only_after_expiry(world, monkeypatch):
    monkeypatch.setattr(apps, "REVERIFY_WINDOW_DAYS", 0)
    _cert(world["db"], world["inst"], "soon", "CERT-SOON", 1)
    with pytest.raises(HTTPException):
        apps.submit_application(ApplicationCreate(instrument_id=str(world["inst"])), current_user=world["owner"])


def test_officer_queue_puts_the_most_urgent_renewal_first(world):
    db, now = world["db"], datetime.now(timezone.utc)
    loc = {"state_code": "WB", "district_code": "319"}
    def app(name, sub_days_ago, expiry_in_days=None):
        db["applications"].insert_one({
            "_id": name, "instrument_id": ObjectId(), "owner_id": ObjectId(), "status": "submitted",
            "assigned_officer_id": None, "submitted_at": now - timedelta(days=sub_days_ago), "history": [],
            **loc, **({"application_type": "renewal", "previous_valid_until": now + timedelta(days=expiry_in_days)}
                      if expiry_in_days is not None else {}),
        })
    app("first-timer-new", 1)
    app("first-timer-old", 9)
    app("renews-in-20", 2, 20)
    app("expired-5-days-ago", 3, -5)
    app("renews-in-3", 4, 3)
    officer = {"_id": ObjectId(), "role": "lmo", "jurisdiction": {"state_code": "WB", "district_code": "319"}}
    ids = [a.id for a in apps.list_applications(status=None, mine=False, current_user=officer)]
    assert ids == ["expired-5-days-ago", "renews-in-3", "renews-in-20", "first-timer-new", "first-timer-old"]


def test_valid_newest_certificate_blocks_even_if_an_expired_one_is_named(world):
    _cert(world["db"], world["inst"], "old", "CERT-OLD", -400)
    _cert(world["db"], world["inst"], "live", "CERT-LIVE", 200)
    with pytest.raises(HTTPException) as exc:
        apps.submit_application(
            ApplicationCreate(instrument_id=str(world["inst"]), previous_certificate_id="old"), current_user=world["owner"]
        )
    assert exc.value.status_code == 409


def test_expired_certificate_allows_renewal(world):
    _cert(world["db"], world["inst"], "gone", "CERT-GONE", -1)
    out = apps.submit_application(ApplicationCreate(instrument_id=str(world["inst"])), current_user=world["owner"])
    assert out.application_type == "renewal" and out.previous_cert_no == "CERT-GONE"


@pytest.mark.parametrize("status", ["submitted", "scheduled", "inspected"])
def test_second_application_while_one_is_open_is_a_409(world, status):
    world["db"]["applications"].insert_one({"instrument_id": world["inst"], "status": status})
    with pytest.raises(HTTPException) as exc:
        apps.submit_application(ApplicationCreate(instrument_id=str(world["inst"])), current_user=world["owner"])
    assert exc.value.status_code == 409
    assert world["db"]["applications"].count_documents({}) == 1


@pytest.mark.parametrize("status", ["certified", "rejected", "expiring", "expired"])
def test_finished_applications_do_not_block_a_new_one(world, status):
    world["db"]["applications"].insert_one({"instrument_id": world["inst"], "status": status})
    out = apps.submit_application(ApplicationCreate(instrument_id=str(world["inst"])), current_user=world["owner"])
    assert out.status == "submitted"


def test_other_instrument_is_not_blocked(world):
    world["db"]["applications"].insert_one({"instrument_id": world["inst"], "status": "submitted"})
    apps.submit_application(ApplicationCreate(instrument_id=str(world["inst2"])), current_user=world["owner"])


def test_legacy_application_without_type_reads_as_initial(world):
    doc = {"_id": ObjectId(), "instrument_id": world["inst"], "owner_id": world["owner"]["_id"], "status": "certified",
           "submitted_at": datetime.now(timezone.utc)}
    assert apps.to_application_out(doc).application_type == "initial"


def test_serialized_certificate_exposes_renewal_trail(world):
    now = datetime.now(timezone.utc)
    cert = {"_id": "c2", "cert_no": "CERT-2", "application_id": ObjectId(), "instrument_id": world["inst"],
            "application_type": "renewal", "previous_certificate_id": "c1", "previous_cert_no": "CERT-1",
            "issued_at": now, "valid_until": now + timedelta(days=365)}
    out = certs._serialize_cert(cert)
    assert out["instrument_id"] == str(world["inst"])
    assert (out["application_type"], out["previous_certificate_id"], out["previous_cert_no"]) == ("renewal", "c1", "CERT-1")
    legacy = certs._serialize_cert({**cert, "application_type": None, "previous_certificate_id": None, "previous_cert_no": None})
    assert legacy["application_type"] == "initial"


# ---- chained validity ----------------------------------------------------

from app.services.cert_generator import compute_validity


def test_first_certificate_starts_now():
    now = datetime(2026, 10, 17, tzinfo=timezone.utc)
    start, end = compute_validity(now, None)
    assert start == now and end == now + timedelta(days=365)


def test_renewal_inside_window_continues_from_old_expiry():
    now = datetime(2026, 10, 17, tzinfo=timezone.utc)
    old_end = now + timedelta(days=12)
    start, end = compute_validity(now, old_end.replace(tzinfo=None))  # Mongo hands back naive datetimes
    assert start == old_end and end == old_end + timedelta(days=365)


def test_renewal_after_expiry_starts_now():
    now = datetime(2026, 10, 17, tzinfo=timezone.utc)
    start, end = compute_validity(now, now - timedelta(days=3))
    assert start == now and end == now + timedelta(days=365)


# ---- public verify page: re-verification in progress ---------------------

@pytest.fixture
def verify_world(monkeypatch):
    db = mongomock.MongoClient()["verify"]
    monkeypatch.setattr(certs, "certificates_col", db["certificates"])
    monkeypatch.setattr(certs, "applications_col", db["applications"])
    monkeypatch.setattr(certs, "instruments_col", db["instruments"])
    monkeypatch.setattr(certs, "users_col", db["users"])
    monkeypatch.setattr(certs, "format_location", lambda loc: "Main Rd")
    inst = db["instruments"].insert_one({"type": "Scale", "uiid": "LM-9", "manufacturer": "A", "model": "B", "location": {}}).inserted_id
    return db, inst


def _issue(db, inst, cert_id, days_left):
    app_id = db["applications"].insert_one({"instrument_id": inst, "owner_id": ObjectId(), "status": "certified",
                                            "submitted_at": datetime.now(timezone.utc)}).inserted_id
    now = datetime.now(timezone.utc)
    db["certificates"].insert_one({"_id": cert_id, "cert_no": "CERT-" + cert_id.upper(), "application_id": app_id,
                                   "instrument_id": inst, "issued_at": now - timedelta(days=300),
                                   "valid_until": now + timedelta(days=days_left)})


def test_expired_certificate_with_open_application_shows_reverification(verify_world):
    db, inst = verify_world
    _issue(db, inst, "gone", -2)
    db["applications"].insert_one({"instrument_id": inst, "status": "scheduled", "submitted_at": datetime.now(timezone.utc)})
    out = certs.verify_certificate("gone")
    assert out["valid"] and out["certificate"]["is_expired"]
    assert out["reverification"]["in_progress"] is True and out["reverification"]["status"] == "scheduled"
    assert "_instrument_id" not in out


def test_expired_certificate_without_open_application_has_no_block(verify_world):
    db, inst = verify_world
    _issue(db, inst, "gone", -2)
    assert "reverification" not in certs.verify_certificate("gone")


def test_valid_certificate_never_shows_reverification(verify_world):
    db, inst = verify_world
    _issue(db, inst, "live", 100)
    db["applications"].insert_one({"instrument_id": inst, "status": "submitted", "submitted_at": datetime.now(timezone.utc)})
    out = certs.verify_certificate("live")
    assert "reverification" not in out and "_instrument_id" not in out


def test_serialized_certificate_has_valid_from_and_window(world):
    now = datetime.now(timezone.utc)
    cert = {"_id": "c", "cert_no": "C", "application_id": ObjectId(), "instrument_id": world["inst"],
            "issued_at": now, "valid_from": now + timedelta(days=10), "valid_until": now + timedelta(days=375)}
    out = certs._serialize_cert(cert)
    assert out["valid_from"] > out["verified_on"]
    assert datetime.fromisoformat(out["valid_until"]) - datetime.fromisoformat(out["renewal_opens_on"]) == timedelta(days=certs.REVERIFY_WINDOW_DAYS)
    assert certs._serialize_cert({k: v for k, v in cert.items() if k != "valid_from"})["valid_from"] == out["verified_on"]
