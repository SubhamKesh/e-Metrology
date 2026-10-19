"""#10 Profile editing, profile picture and the required documents for an application."""
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.security import create_access_token

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
JPG = b"\xff\xd8\xff\xe0" + b"0" * 64
PDF = b"%PDF-1.4\n" + b"0" * 64
EXE = b"MZ" + b"0" * 64


@pytest.fixture(autouse=True)
def fake_storage(monkeypatch):
    """Never reach Cloudinary: record what would be uploaded and hand back a fake link."""
    sent = []

    def fake_upload(data, public_id, resource_type="image"):
        sent.append({"public_id": public_id, "resource_type": resource_type, "size": len(data)})
        return f"https://files.example/{resource_type}/{public_id}"

    import app.routers.auth as auth_mod
    import app.routers.instrument_documents as docs_mod

    monkeypatch.setattr(auth_mod, "upload_bytes", fake_upload)
    monkeypatch.setattr(docs_mod, "upload_bytes", fake_upload)
    return sent


@pytest.fixture
def people(client):
    import app.config.db as dbmod

    def make(role, name, **extra):
        doc = {"name": name, "email": f"{name.lower()}@example.com", "role": role, "status": "active",
               "token_version": 0, "contact": "9876543210", "is_phone_verified": True, **extra}
        if role in ("lmo", "gatc"):
            doc["jurisdiction"] = {"state_code": "WB", "district_code": "319"}
        doc["_id"] = dbmod.users_col.insert_one(doc).inserted_id
        return {"Authorization": f"Bearer {create_access_token(str(doc['_id']), 0)}", "_id": doc["_id"]}

    out = {role: make(role, role.title()) for role in ("owner", "lmo", "admin")}
    out["other_owner"] = make("owner", "Other")
    return out


def h(person):
    return {"Authorization": person["Authorization"]}


# ------------------------------------------------------------------ profile editing


def test_me_has_no_picture_until_one_is_set(client, people):
    assert client.get("/api/v1/auth/me", headers=h(people["owner"])).json()["avatar_url"] is None


def test_edit_name_phone_and_organisation(client, people):
    r = client.patch("/api/v1/auth/me", headers=h(people["owner"]),
                     json={"name": "  New Name ", "contact": "9123456780", "org_name": "New Org"})
    assert r.status_code == 200
    body = r.json()
    assert (body["name"], body["contact"], body["org_name"]) == ("New Name", "9123456780", "New Org")
    assert body["is_phone_verified"] is False  # a new number has to be verified again
    assert body["email"] == "owner@example.com"


def test_only_the_fields_sent_change_and_the_phone_stays_verified_if_unchanged(client, people):
    r = client.patch("/api/v1/auth/me", headers=h(people["owner"]), json={"name": "Renamed"})
    assert r.status_code == 200 and r.json()["contact"] == "9876543210" and r.json()["is_phone_verified"] is True
    again = client.patch("/api/v1/auth/me", headers=h(people["owner"]), json={"contact": "9876543210"})
    assert again.json()["is_phone_verified"] is True


def test_email_role_and_status_cannot_be_changed_here(client, people):
    client.patch("/api/v1/auth/me", headers=h(people["owner"]),
                 json={"email": "x@y.com", "role": "admin", "status": "rejected", "name": "Same"})
    me = client.get("/api/v1/auth/me", headers=h(people["owner"])).json()
    assert (me["email"], me["role"], me["status"]) == ("owner@example.com", "owner", "active")


@pytest.mark.parametrize("body", [{"name": "   "}, {"contact": "12345"}, {"name": "x" * 500}])
def test_bad_values_are_refused(client, people, body):
    assert client.patch("/api/v1/auth/me", headers=h(people["owner"]), json=body).status_code == 422


def test_an_officer_cannot_change_their_organisation(client, people):
    assert client.patch("/api/v1/auth/me", headers=h(people["lmo"]), json={"org_name": "Mine now"}).status_code == 403
    assert client.patch("/api/v1/auth/me", headers=h(people["lmo"]), json={"name": "Officer Renamed"}).status_code == 200


def test_the_phone_can_be_cleared(client, people):
    assert client.patch("/api/v1/auth/me", headers=h(people["owner"]), json={"contact": ""}).json()["contact"] is None


def test_profile_edit_needs_sign_in(client):
    assert client.patch("/api/v1/auth/me", json={"name": "A"}).status_code in (401, 403)


def test_profile_changes_are_audited(client, people):
    import app.config.db as dbmod

    client.patch("/api/v1/auth/me", headers=h(people["owner"]), json={"name": "Audited", "contact": "9123456780"})
    row = dbmod.db["audit_logs"].find_one({"event": "profile_updated"})
    assert row["outcome"] == "success" and row["detail"] == "fields=contact,name"
    client.patch("/api/v1/auth/me", headers=h(people["owner"]), json={"name": "Audited"})  # nothing changed
    assert dbmod.db["audit_logs"].count_documents({"event": "profile_updated"}) == 1


# ------------------------------------------------------------------ profile picture


@pytest.mark.parametrize("data,name", [(PNG, "me.png"), (JPG, "me.jpg")])
def test_set_and_remove_a_profile_picture(client, people, fake_storage, data, name):
    r = client.post("/api/v1/auth/me/avatar", headers=h(people["owner"]), files={"file": (name, data, "application/octet-stream")})
    assert r.status_code == 200 and r.json()["avatar_url"].startswith("https://files.example/image/avatar_")
    assert fake_storage[-1]["resource_type"] == "image"
    assert client.get("/api/v1/auth/me", headers=h(people["owner"])).json()["avatar_url"] == r.json()["avatar_url"]
    gone = client.delete("/api/v1/auth/me/avatar", headers=h(people["owner"]))
    assert gone.status_code == 200 and gone.json()["avatar_url"] is None


def test_a_new_picture_replaces_the_old_one(client, people):
    a = client.post("/api/v1/auth/me/avatar", headers=h(people["owner"]), files={"file": ("a.png", PNG)}).json()["avatar_url"]
    b = client.post("/api/v1/auth/me/avatar", headers=h(people["owner"]), files={"file": ("b.png", PNG)}).json()["avatar_url"]
    assert a != b and client.get("/api/v1/auth/me", headers=h(people["owner"])).json()["avatar_url"] == b


def test_the_picture_must_really_be_an_image(client, people, fake_storage):
    for name, data in (("fake.png", EXE), ("doc.pdf", PDF), ("empty.png", b"")):
        r = client.post("/api/v1/auth/me/avatar", headers=h(people["owner"]), files={"file": (name, data)})
        assert r.status_code in (400, 415)
    assert fake_storage == []


def test_a_picture_over_2_mb_is_refused(client, people):
    r = client.post("/api/v1/auth/me/avatar", headers=h(people["owner"]), files={"file": ("big.png", PNG + b"0" * (2 * 1024 * 1024))})
    assert r.status_code == 413


def test_a_storage_failure_is_a_clean_error(client, people, monkeypatch):
    import app.routers.auth as auth_mod

    def boom(*a, **k):
        raise RuntimeError("cloudinary down")

    monkeypatch.setattr(auth_mod, "upload_bytes", boom)
    r = client.post("/api/v1/auth/me/avatar", headers=h(people["owner"]), files={"file": ("a.png", PNG)})
    assert r.status_code == 502
    assert client.get("/api/v1/auth/me", headers=h(people["owner"])).json()["avatar_url"] is None


def test_every_role_may_have_a_picture(client, people):
    for who in ("owner", "lmo", "admin"):
        assert client.post("/api/v1/auth/me/avatar", headers=h(people[who]), files={"file": ("a.png", PNG)}).status_code == 200


# ------------------------------------------------------------------ required documents


@pytest.fixture(autouse=True)
def documents_required(client, monkeypatch):
    """Undo the suite-wide switch that skips the document check."""
    import app.config.db as dbmod
    import app.routers.applications as apps
    from app.services.documents import missing_required_documents

    monkeypatch.setattr(apps, "missing_required_documents", missing_required_documents)
    # Submitting an application points these at the in-memory database and mutes mail and live updates.
    for name in ("applications_col", "certificates_col", "instruments_col", "users_col"):
        monkeypatch.setattr(apps, name, getattr(dbmod, name))
    monkeypatch.setattr(apps, "notify_application_submitted", lambda doc: None)
    monkeypatch.setattr(apps, "broadcast_threadsafe", lambda *a, **k: None)


@pytest.fixture
def instrument(client, people):
    import app.config.db as dbmod

    def make(owner="owner", uiid="LM-000001"):
        return str(dbmod.instruments_col.insert_one({
            "owner_id": people[owner]["_id"], "uiid": uiid, "type": "Platform Scale", "manufacturer": "M", "model": "X",
            "capacity": "30 kg", "serial_no": uiid, "location": {"state_code": "WB", "district_code": "319", "address_line": "a"},
        }).inserted_id)

    return make


def url(i, slot=""):
    return f"/api/v1/instruments/{i}/documents" + (f"/{slot}" if slot else "")


def put(client, who, i, slot, data=PDF, name="a.pdf"):
    return client.post(url(i, slot), headers=h(who), files={"file": (name, data)})


def certify(i, issued_days_ago=355, valid_days_left=10):
    """Give the instrument a certificate, so the next application is a re-verification."""
    import app.config.db as dbmod
    from bson import ObjectId

    now = datetime.now(timezone.utc)
    dbmod.certificates_col.insert_one({
        "_id": "c1", "instrument_id": ObjectId(i), "application_id": ObjectId(), "cert_no": "CERT-1",
        "issued_at": now - timedelta(days=issued_days_ago), "valid_until": now + timedelta(days=valid_days_left),
    })


def slots(client, who, i):
    body = client.get(url(i), headers=h(who)).json()
    return body, {s["slot"]: s for s in body["slots"]}


def test_a_first_verification_needs_the_tax_invoice_and_the_owner_id(client, people, instrument):
    i = instrument()
    body, by = slots(client, people["owner"], i)
    assert body["application_type"] == "initial" and body["complete"] is False and body["locked"] is False
    assert [s["slot"] for s in body["slots"]] == ["tax_invoice", "owner_id_proof"]
    assert all(s["required"] and s["document"] is None for s in body["slots"])
    assert by["tax_invoice"]["label"] == "Tax invoice" and by["owner_id_proof"]["label"] == "Owner ID proof"


def test_a_re_verification_needs_only_the_previous_certificate(client, people, instrument):
    i = instrument()
    certify(i)
    body, _ = slots(client, people["owner"], i)
    assert body["application_type"] == "renewal" and [s["slot"] for s in body["slots"]] == ["previous_certificate"]
    assert body["slots"][0]["required"] is True


def test_upload_fills_a_slot_and_replaces_on_a_second_upload(client, people, instrument, fake_storage):
    i = instrument()
    r = put(client, people["owner"], i, "tax_invoice", name="Invoice 1.pdf")
    assert r.status_code == 201
    d = r.json()
    assert (d["slot"], d["label"], d["content_type"], d["filename"]) == ("tax_invoice", "Tax invoice", "application/pdf", "Invoice 1.pdf")
    assert d["url"].endswith(".pdf") and fake_storage[-1]["resource_type"] == "raw"
    second = put(client, people["owner"], i, "tax_invoice", data=JPG, name="scan.jpg").json()
    assert fake_storage[-1]["resource_type"] == "image"
    body, by = slots(client, people["owner"], i)
    assert by["tax_invoice"]["document"]["id"] == second["id"] and by["tax_invoice"]["document"]["filename"] == "scan.jpg"
    import app.config.db as dbmod

    assert dbmod.db["instrument_documents"].count_documents({}) == 1  # replaced, not added
    assert body["complete"] is False  # the ID proof is still missing
    put(client, people["owner"], i, "owner_id_proof", data=PNG, name="id.png")
    assert slots(client, people["owner"], i)[0]["complete"] is True


def test_there_is_no_slot_for_anything_else(client, people, instrument):
    i = instrument()
    assert put(client, people["owner"], i, "other").status_code == 404
    assert put(client, people["owner"], i, "nonsense").status_code == 404


def test_a_slot_that_does_not_apply_is_refused(client, people, instrument):
    i = instrument()
    assert put(client, people["owner"], i, "previous_certificate").status_code == 422  # first verification
    j = instrument(uiid="LM-000002")
    certify(j)
    assert put(client, people["owner"], j, "tax_invoice").status_code == 422  # re-verification


def test_the_stored_filename_is_cleaned(client, people, instrument):
    i = instrument()
    r = put(client, people["owner"], i, "tax_invoice", data=PNG, name="../../etc/<evil>.exe")
    assert "/" not in r.json()["filename"] and "<" not in r.json()["filename"] and r.json()["filename"].endswith(".png")


@pytest.mark.parametrize("data", [EXE, b"", b"<html>hi</html>", b"RIFF0000WEBP" + b"0" * 20])
def test_only_pdf_jpg_png_are_accepted(client, people, instrument, fake_storage, data):
    i = instrument()
    assert put(client, people["owner"], i, "tax_invoice", data=data).status_code in (400, 415)
    assert fake_storage == []


def test_a_document_over_5_mb_is_refused(client, people, instrument):
    i = instrument()
    assert put(client, people["owner"], i, "tax_invoice", data=PDF + b"0" * (5 * 1024 * 1024)).status_code == 413


def test_removing_a_document(client, people, instrument):
    i = instrument()
    put(client, people["owner"], i, "tax_invoice")
    assert client.delete(url(i, "tax_invoice"), headers=h(people["owner"])).status_code == 204
    assert slots(client, people["owner"], i)[1]["tax_invoice"]["document"] is None
    assert client.delete(url(i, "tax_invoice"), headers=h(people["owner"])).status_code == 404


def test_only_the_owner_of_the_instrument_may_change_documents(client, people, instrument):
    i = instrument()
    put(client, people["owner"], i, "tax_invoice")
    assert put(client, people["other_owner"], i, "owner_id_proof").status_code == 403
    assert client.delete(url(i, "tax_invoice"), headers=h(people["other_owner"])).status_code == 403
    for who in ("lmo", "admin"):  # officers and admins view, they do not add or remove
        assert put(client, people[who], i, "owner_id_proof").status_code == 403
        assert client.delete(url(i, "tax_invoice"), headers=h(people[who])).status_code == 403
    assert client.post(url(i, "tax_invoice"), files={"file": ("a.pdf", PDF)}).status_code in (401, 403)


def test_who_can_see_the_documents(client, people, instrument):
    import app.config.db as dbmod

    i = instrument()
    put(client, people["owner"], i, "tax_invoice")
    assert client.get(url(i), headers=h(people["admin"])).status_code == 200
    assert client.get(url(i), headers=h(people["other_owner"])).status_code == 403
    assert client.get(url(i), headers=h(people["lmo"])).status_code == 403  # nothing for them to review yet
    dbmod.applications_col.insert_one({"instrument_id": dbmod.instruments_col.find_one()["_id"], "assigned_officer_id": None, "status": "submitted"})
    assert client.get(url(i), headers=h(people["lmo"])).status_code == 200  # now it is in the queue
    assert client.get(url(i)).status_code in (401, 403)


def test_bad_ids_and_unknown_instruments(client, people):
    assert client.get(url("nope"), headers=h(people["owner"])).status_code == 400
    assert client.get(url("0" * 24), headers=h(people["owner"])).status_code == 404


def test_documents_are_locked_while_an_application_is_open(client, people, instrument):
    import app.config.db as dbmod

    i = instrument()
    put(client, people["owner"], i, "tax_invoice")
    put(client, people["owner"], i, "owner_id_proof")
    assert client.post("/api/v1/applications", headers=h(people["owner"]), json={"instrument_id": i}).status_code == 201
    assert slots(client, people["owner"], i)[0]["locked"] is True
    assert put(client, people["owner"], i, "tax_invoice").status_code == 409
    assert client.delete(url(i, "owner_id_proof"), headers=h(people["owner"])).status_code == 409
    dbmod.applications_col.update_many({}, {"$set": {"status": "rejected"}})  # finished: unlocked again
    assert put(client, people["owner"], i, "tax_invoice").status_code == 201


# ---- the application cannot be submitted without them


def apply(client, who, i):
    return client.post("/api/v1/applications", headers=h(who), json={"instrument_id": i})


def test_a_first_application_is_refused_until_both_documents_are_uploaded(client, people, instrument):
    i = instrument()
    r = apply(client, people["owner"], i)
    assert r.status_code == 422 and "Tax invoice, Owner ID proof" in r.json()["detail"]
    put(client, people["owner"], i, "tax_invoice")
    r = apply(client, people["owner"], i)
    assert r.status_code == 422 and "Owner ID proof" in r.json()["detail"] and "Tax invoice" not in r.json()["detail"]
    put(client, people["owner"], i, "owner_id_proof")
    r = apply(client, people["owner"], i)
    assert r.status_code == 201 and r.json()["application_type"] == "initial"


def test_a_re_verification_is_refused_without_the_previous_certificate(client, people, instrument):
    i = instrument()
    certify(i)
    r = apply(client, people["owner"], i)
    assert r.status_code == 422 and "Previous certificate" in r.json()["detail"]
    put(client, people["owner"], i, "previous_certificate")
    assert apply(client, people["owner"], i).json()["application_type"] == "renewal"


def test_the_invoice_and_id_are_not_asked_for_again_on_a_renewal(client, people, instrument):
    i = instrument()
    certify(i)
    put(client, people["owner"], i, "previous_certificate")
    assert apply(client, people["owner"], i).status_code == 201  # no tax invoice or ID needed


def test_a_previous_certificate_from_an_earlier_renewal_cannot_be_reused(client, people, instrument):
    import app.config.db as dbmod
    from bson import ObjectId

    i = instrument()
    certify(i)
    put(client, people["owner"], i, "previous_certificate")
    # A newer certificate is issued afterwards: the copy uploaded before it no longer counts.
    now = datetime.now(timezone.utc)
    dbmod.certificates_col.insert_one({
        "_id": "c2", "instrument_id": ObjectId(i), "application_id": ObjectId(), "cert_no": "CERT-2",
        "issued_at": now + timedelta(seconds=5), "valid_until": now + timedelta(days=10),
    })
    r = apply(client, people["owner"], i)
    assert r.status_code == 422 and "Previous certificate" in r.json()["detail"]
    _, by = slots(client, people["owner"], i)
    assert by["previous_certificate"]["document"] is None


def test_uploads_and_removals_are_audited(client, people, instrument):
    import app.config.db as dbmod

    i = instrument()
    put(client, people["owner"], i, "owner_id_proof")
    client.delete(url(i, "owner_id_proof"), headers=h(people["owner"]))
    logs = {r["event"]: r for r in dbmod.db["audit_logs"].find({"event": {"$in": ["document_uploaded", "document_deleted"]}})}
    assert logs["document_uploaded"]["detail"] == "instrument=LM-000001 slot=owner_id_proof"
    assert logs["document_deleted"]["detail"] == "instrument=LM-000001 slot=owner_id_proof"
