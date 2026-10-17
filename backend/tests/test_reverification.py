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


def test_cannot_renew_while_certificate_is_still_valid(world):
    _cert(world["db"], world["inst"], "live", "CERT-LIVE", 5)
    with pytest.raises(HTTPException) as exc:
        apps.submit_application(ApplicationCreate(instrument_id=str(world["inst"])), current_user=world["owner"])
    assert exc.value.status_code == 409 and "once it has expired" in exc.value.detail
    assert world["db"]["applications"].count_documents({}) == 0


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
