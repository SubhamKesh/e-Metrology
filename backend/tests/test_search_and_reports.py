"""#7 Search on the lists + CSV/PDF report export.

Covers: every search filter on applications, certificates, instruments and the officer list; that no
filter can widen what a role may see; and that the report downloads hold exactly what the lists show,
for the right roles, with spreadsheet formulas defused, an export limit, and an audit record.
"""
import csv
import io
import re
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.security import create_access_token

APPS = "/api/v1/applications"
CERTS = "/api/v1/certificates/"
INSTR = "/api/v1/instruments"
USERS = "/api/v1/admin/users"
REPORTS = "/api/v1/reports"


def _naive_utc(**delta) -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(**delta)


@pytest.fixture
def world(client, monkeypatch):
    import app.config.db as dbmod
    import app.routers.admin_users as admin_users_mod
    import app.routers.applications as apps_mod
    import app.routers.certificates as certs_mod
    import app.routers.instruments as instruments_mod
    import app.routers.reports as reports_mod

    db = dbmod.db
    for mod, names in [
        (apps_mod, ["applications_col", "instruments_col", "certificates_col", "users_col"]),
        (certs_mod, ["applications_col", "instruments_col", "certificates_col", "users_col"]),
        (instruments_mod, ["applications_col", "instruments_col"]),
        (admin_users_mod, ["users_col"]),
        (reports_mod, ["applications_col", "instruments_col", "certificates_col", "users_col", "states_col", "districts_col"]),
    ]:
        for name in names:
            monkeypatch.setattr(mod, name, db[name.removesuffix("_col")])
    # Listing certificates nudges a background reconciler that would talk to the real database.
    monkeypatch.setattr(certs_mod, "start_reconcile", lambda *a, **k: False)
    # Formatting a place name would query the real (unpatched) database.
    monkeypatch.setattr(certs_mod, "format_location", lambda loc: "Main Road, Murshidabad, West Bengal")

    db["states"].insert_one({"code": "WB", "name": "West Bengal"})
    db["districts"].insert_many([
        {"code": "319", "state_code": "WB", "name": "Murshidabad"},
        {"code": "320", "state_code": "WB", "name": "Nadia"},
    ])

    def user(role, name, email, org=None, jurisdiction=None, status="active"):
        doc = {"name": name, "email": email, "role": role, "status": status, "token_version": 0, "org_name": org}
        if jurisdiction:
            doc["jurisdiction"] = jurisdiction
        doc["_id"] = db["users"].insert_one(doc).inserted_id
        doc["headers"] = {"Authorization": f"Bearer {create_access_token(str(doc['_id']), 0)}"}
        return doc

    w = {
        "db": db, "reports": reports_mod,
        "owner_a": user("owner", "Anil", "a@example.com", org="Alpha Traders"),
        "owner_b": user("owner", "Bina", "b@example.com", org="Beta Stores"),
        "lmo": user("lmo", "Ravi Kumar", "ravi@example.com", jurisdiction={"state_code": "WB", "district_code": "319"}),
        "gatc": user("gatc", "Sita Devi", "sita@example.com", jurisdiction={"state_code": "WB", "district_code": None}, status="pending"),
        "admin": user("admin", "Minister", "admin@example.com"),
    }
    loc = lambda district, addr: {"state_code": "WB", "district_code": district, "address_line": addr}  # noqa: E731
    w["i1"] = db["instruments"].insert_one({
        "owner_id": w["owner_a"]["_id"], "uiid": "LM-24-AAAA0001", "type": "Platform Scale", "manufacturer": "Acme Scales",
        "model": "PS-500", "serial_no": "SER-100", "capacity": "500 kg", "location": loc("319", "Main Road")}).inserted_id
    w["i2"] = db["instruments"].insert_one({
        "owner_id": w["owner_a"]["_id"], "uiid": "LM-24-AAAA0002", "type": "Water Meter", "manufacturer": "=cmd|' /C calc'!A0",
        "model": "WM-1", "serial_no": "SER-200", "capacity": "1.5 m³", "location": loc("319", "Station Road")}).inserted_id
    w["i3"] = db["instruments"].insert_one({
        "owner_id": w["owner_b"]["_id"], "uiid": "LM-24-BBBB0003", "type": "Platform Scale", "manufacturer": "Beta Works",
        "model": "PS-9", "serial_no": "SER-300", "capacity": "100 kg", "location": loc("320", "Market Lane")}).inserted_id

    def application(owner, instrument, status, district, submitted_at, **extra):
        doc = {"owner_id": owner["_id"], "instrument_id": instrument, "status": status, "assigned_officer_id": None,
               "state_code": "WB", "district_code": district, "submitted_at": submitted_at, "history": [], **extra}
        return db["applications"].insert_one(doc).inserted_id

    # 20:00 UTC on 17 Oct is 01:30 on 18 Oct in India: the day boundary tests below rely on it.
    w["app0"] = application(w["owner_a"], w["i1"], "expired", "319", datetime(2025, 8, 1, 6, 0))
    w["app1"] = application(w["owner_a"], w["i1"], "submitted", "319", datetime(2026, 10, 17, 20, 0),
                            application_type="renewal", previous_cert_no="CERT-OLD-1",
                            previous_valid_until=_naive_utc(days=5))
    w["app2"] = application(w["owner_a"], w["i2"], "certified", "319", datetime(2026, 9, 1, 6, 0))
    w["app3"] = application(w["owner_b"], w["i3"], "certified", "320", datetime(2026, 9, 2, 6, 0))

    def certificate(cert_id, app_id, instrument, cert_no, seal, issued, valid_until, **extra):
        db["certificates"].insert_one({
            "_id": cert_id, "application_id": app_id, "instrument_id": instrument, "cert_no": cert_no,
            "seal_number": seal, "issued_at": issued, "valid_until": valid_until, **extra})

    w["issued_valid"] = _naive_utc(days=-60)
    certificate("c-valid", w["app2"], w["i2"], "CERT-20260901-AAA111", "SEAL-0001", w["issued_valid"], _naive_utc(days=300))
    certificate("c-expiring", w["app3"], w["i3"], "CERT-20260902-BBB222", "SEAL-0002", _naive_utc(days=-350),
                _naive_utc(days=10), application_type="renewal", previous_cert_no="CERT-PREV-9")
    certificate("c-expired", w["app0"], w["i1"], "CERT-20250801-CCC333", None, _naive_utc(days=-400), _naive_utc(days=-35))
    return w


def _get(client, path, who, **params):
    return client.get(path, params={k: v for k, v in params.items() if v is not None}, headers=who["headers"])


def _ids(response):
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()}


def _csv(response):
    assert response.status_code == 200, response.text
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    header, data = rows[0], rows[1:]
    return header, [dict(zip(header, r)) for r in data]


# ------------------------------------------------------------------ applications: search

def test_unfiltered_application_list_is_unchanged(client, world):
    assert _ids(_get(client, APPS, world["admin"])) == {str(world[k]) for k in ("app0", "app1", "app2", "app3")}


@pytest.mark.parametrize("text, expected", [
    ("LM-24-AAAA0001", {"app0", "app1"}),       # UIID
    ("lm-24-aaaa0002", {"app2"}),               # case-insensitive
    ("ser-300", {"app3"}),                      # serial number
    ("acme", {"app0", "app1"}),                 # manufacturer
    ("PS-9", {"app3"}),                         # model
    ("platform scale", {"app0", "app1", "app3"}),  # type
    ("  ps-500  ", {"app0", "app1"}),           # surrounding spaces are ignored
    ("CERT-OLD-1", {"app1"}),                   # certificate being renewed
    ("nothing-like-this", set()),
    ("LM.*", set()),                            # matched literally, never as a pattern
    ("(", set()),
])
def test_application_text_search(client, world, text, expected):
    assert _ids(_get(client, APPS, world["admin"], q=text)) == {str(world[k]) for k in expected}


def test_application_search_by_full_application_id(client, world):
    assert _ids(_get(client, APPS, world["admin"], q=str(world["app3"]))) == {str(world["app3"])}


@pytest.mark.parametrize("params, expected", [
    ({"application_type": "renewal"}, {"app1"}),
    ({"application_type": "initial"}, {"app0", "app2", "app3"}),   # records with no type count as initial
    ({"status": "certified"}, {"app2", "app3"}),
    ({"instrument_type": "Water Meter"}, {"app2"}),
    ({"state_code": "WB", "district_code": "320"}, {"app3"}),
    ({"district_code": "999"}, set()),
    ({"date_from": "2026-10-18", "date_to": "2026-10-18"}, {"app1"}),   # India day, not UTC day
    ({"date_from": "2026-10-17", "date_to": "2026-10-17"}, set()),
    ({"date_from": "2026-09-01", "date_to": "2026-09-02"}, {"app2", "app3"}),
    ({"date_from": "2026-09-02"}, {"app1", "app3"}),
    ({"q": "platform", "status": "certified"}, {"app3"}),            # filters combine with AND
    ({"q": "platform", "instrument_type": "Water Meter"}, set()),
])
def test_application_filters(client, world, params, expected):
    assert _ids(_get(client, APPS, world["admin"], **params)) == {str(world[k]) for k in expected}


@pytest.mark.parametrize("params, code", [
    ({"date_from": "2026-10-18", "date_to": "2026-10-17"}, 400),
    ({"instrument_type": "Flying Carpet"}, 400),
    ({"application_type": "bogus"}, 422),
    ({"date_from": "yesterday"}, 422),
    ({"q": "x" * 101}, 422),
])
def test_application_bad_filters_are_rejected(client, world, params, code):
    assert _get(client, APPS, world["admin"], **params).status_code == code


def test_filters_never_widen_what_a_role_may_see(client, world):
    a, b = world["owner_a"], world["owner_b"]
    assert _ids(_get(client, APPS, a, q="LM-24-BBBB0003")) == set()                 # someone else's instrument
    assert _ids(_get(client, APPS, a, district_code="320")) == set()
    assert _ids(_get(client, APPS, b)) == {str(world["app3"])}
    # The officer's list is the claimable queue in their own district, whatever they ask for.
    assert _ids(_get(client, APPS, world["lmo"])) == {str(world["app1"])}
    assert _ids(_get(client, APPS, world["lmo"], q="acme")) == {str(world["app1"])}
    assert _ids(_get(client, APPS, world["lmo"], q="ser-300")) == set()
    assert _ids(_get(client, APPS, world["lmo"], state_code="OD")) == set()
    assert _ids(_get(client, APPS, world["lmo"], district_code="320", status="certified")) == set()
    assert _ids(_get(client, APPS, world["lmo"], mine="true")) == set()


# ------------------------------------------------------------------ certificates: search

def test_unfiltered_certificate_list_is_unchanged(client, world):
    assert _ids(_get(client, CERTS, world["admin"])) == {"c-valid", "c-expiring", "c-expired"}


@pytest.mark.parametrize("text, expected", [
    ("cert-20260901-aaa111", {"c-valid"}),
    ("SEAL-0002", {"c-expiring"}),
    ("c-valid", {"c-valid"}),                    # the certificate id
    ("acme", {"c-expired"}),                     # the instrument's manufacturer
    ("LM-24-BBBB0003", {"c-expiring"}),
    ("PREV-9", {"c-expiring"}),                  # the certificate it renews
    ("platform", {"c-expiring", "c-expired"}),
    ("zzz", set()),
    (".*", set()),
])
def test_certificate_text_search(client, world, text, expected):
    assert _ids(_get(client, CERTS, world["admin"], q=text)) == expected


@pytest.mark.parametrize("params, expected", [
    ({"status": "valid"}, {"c-valid", "c-expiring"}),
    ({"status": "expiring"}, {"c-expiring"}),
    ({"status": "expired"}, {"c-expired"}),
    ({"application_type": "renewal"}, {"c-expiring"}),
    ({"application_type": "initial"}, {"c-valid", "c-expired"}),
    ({"instrument_type": "Water Meter"}, {"c-valid"}),
    ({"q": "platform", "status": "valid"}, {"c-expiring"}),
])
def test_certificate_filters(client, world, params, expected):
    assert _ids(_get(client, CERTS, world["admin"], **params)) == expected


def test_certificate_issue_date_range_uses_india_days(client, world):
    ist_day = (world["issued_valid"] + timedelta(hours=5, minutes=30)).date().isoformat()
    assert _ids(_get(client, CERTS, world["admin"], date_from=ist_day, date_to=ist_day)) == {"c-valid"}


@pytest.mark.parametrize("params, code", [
    ({"status": "soon"}, 422),
    ({"instrument_type": "Flying Carpet"}, 400),
    ({"date_from": "2026-02-02", "date_to": "2026-02-01"}, 400),
])
def test_certificate_bad_filters_are_rejected(client, world, params, code):
    assert _get(client, CERTS, world["admin"], **params).status_code == code


def test_certificate_filters_never_widen_scope(client, world):
    assert _ids(_get(client, CERTS, world["owner_a"])) == {"c-valid", "c-expired"}
    assert _ids(_get(client, CERTS, world["owner_a"], q="SEAL-0002")) == set()
    assert _ids(_get(client, CERTS, world["owner_a"], status="expiring")) == set()
    assert _ids(_get(client, CERTS, world["lmo"])) == {"c-valid", "c-expired"}    # district 319 only
    assert _ids(_get(client, CERTS, world["lmo"], q="LM-24-BBBB0003")) == set()


# ------------------------------------------------------------------ instruments + officers: search

def test_instrument_search_and_scope(client, world):
    ids = lambda r: {i["uiid"] for i in r.json()}  # noqa: E731
    assert ids(_get(client, INSTR, world["owner_a"])) == {"LM-24-AAAA0001", "LM-24-AAAA0002"}
    assert ids(_get(client, INSTR, world["owner_a"], q="acme")) == {"LM-24-AAAA0001"}
    assert ids(_get(client, INSTR, world["owner_a"], type="Water Meter")) == {"LM-24-AAAA0002"}
    assert ids(_get(client, INSTR, world["owner_a"], q="SER-300")) == set()                 # not theirs
    assert ids(_get(client, INSTR, world["admin"], q="SER-300")) == {"LM-24-BBBB0003"}
    assert ids(_get(client, INSTR, world["admin"], state_code="WB", district_code="320")) == {"LM-24-BBBB0003"}
    assert ids(_get(client, INSTR, world["admin"], q="platform", type="Water Meter")) == set()
    assert _get(client, INSTR, world["admin"], type="Flying Carpet").status_code == 400
    assert _get(client, INSTR, world["lmo"], q="acme").status_code == 403


def test_officer_list_search(client, world):
    names = lambda r: {u["name"] for u in r.json()}  # noqa: E731
    assert names(_get(client, USERS, world["admin"])) == {"Ravi Kumar", "Sita Devi"}
    assert names(_get(client, USERS, world["admin"], q="ravi")) == {"Ravi Kumar"}
    assert names(_get(client, USERS, world["admin"], q="SITA@EXAMPLE")) == {"Sita Devi"}
    assert names(_get(client, USERS, world["admin"], role="gatc")) == {"Sita Devi"}
    assert names(_get(client, USERS, world["admin"], status="pending")) == {"Sita Devi"}
    assert names(_get(client, USERS, world["admin"], status="active")) == {"Ravi Kumar"}
    assert names(_get(client, USERS, world["admin"], q=".*")) == set()
    assert _get(client, USERS, world["admin"], status="bogus").status_code == 422
    assert _get(client, USERS, world["owner_a"]).status_code == 403


# ------------------------------------------------------------------ reports: CSV

def test_applications_csv_holds_what_the_list_shows(client, world):
    r = _get(client, f"{REPORTS}/applications", world["admin"])
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert re.fullmatch(r'attachment; filename="maapsetu-applications-\d{8}-\d{4}\.csv"', r.headers["content-disposition"])
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-report-rows"] == "4" and r.headers["x-report-total"] == "4" and r.headers["x-report-truncated"] == "false"
    header, rows = _csv(r)
    assert header[0] == "Application ID"
    assert {row["Application ID"] for row in rows} == _ids(_get(client, APPS, world["admin"]))


def test_applications_csv_follows_the_filters_and_names_places(client, world):
    _, rows = _csv(_get(client, f"{REPORTS}/applications", world["admin"], application_type="renewal"))
    assert len(rows) == 1
    row = rows[0]
    assert row["Type"] == "Re-verification" and row["Status"] == "Submitted"
    assert row["Instrument UIID"] == "LM-24-AAAA0001" and row["Instrument type"] == "Platform Scale"
    assert row["State"] == "West Bengal" and row["District"] == "Murshidabad"
    assert row["Renews certificate"] == "CERT-OLD-1"
    assert row["Applied on"] == "18 Oct 2026, 01:30"
    _, rows = _csv(_get(client, f"{REPORTS}/applications", world["admin"], q="platform", status="certified"))
    assert [r["Instrument UIID"] for r in rows] == ["LM-24-BBBB0003"]


def test_owner_organisation_column_is_for_admins_only(client, world):
    header, rows = _csv(_get(client, f"{REPORTS}/applications", world["admin"]))
    assert "Owner organisation" in header
    assert {r["Owner organisation"] for r in rows} == {"Alpha Traders", "Beta Stores"}
    header, _ = _csv(_get(client, f"{REPORTS}/applications", world["owner_a"]))
    assert "Owner organisation" not in header and "Assigned officer" not in header


def test_reports_never_widen_scope(client, world):
    _, rows = _csv(_get(client, f"{REPORTS}/applications", world["owner_a"]))
    assert "LM-24-BBBB0003" not in {r["Instrument UIID"] for r in rows} and len(rows) == 3
    _, rows = _csv(_get(client, f"{REPORTS}/applications", world["owner_a"], q="LM-24-BBBB0003"))
    assert rows == []
    _, rows = _csv(_get(client, f"{REPORTS}/applications", world["lmo"]))          # the district queue
    assert [r["Application ID"] for r in rows] == [str(world["app1"])]
    _, rows = _csv(_get(client, f"{REPORTS}/applications", world["lmo"], mine="true"))
    assert rows == []
    _, rows = _csv(_get(client, f"{REPORTS}/certificates", world["owner_a"]))
    assert {r["Certificate no."] for r in rows} == {"CERT-20260901-AAA111", "CERT-20250801-CCC333"}
    _, rows = _csv(_get(client, f"{REPORTS}/certificates", world["lmo"], q="BBB222"))
    assert rows == []


def test_certificates_csv(client, world):
    _, rows = _csv(_get(client, f"{REPORTS}/certificates", world["admin"]))
    by_no = {r["Certificate no."]: r for r in rows}
    assert {k: v["Status"] for k, v in by_no.items()} == {
        "CERT-20260901-AAA111": "Valid", "CERT-20260902-BBB222": "Expiring soon", "CERT-20250801-CCC333": "Expired",
    }
    renewal = by_no["CERT-20260902-BBB222"]
    assert renewal["Type"] == "Re-verification" and renewal["Renews certificate"] == "CERT-PREV-9"
    assert renewal["Seal / stamp no."] == "SEAL-0002" and renewal["District"] == "Nadia"
    assert by_no["CERT-20250801-CCC333"]["Seal / stamp no."] == ""
    _, rows = _csv(_get(client, f"{REPORTS}/certificates", world["admin"], status="expired"))
    assert [r["Certificate no."] for r in rows] == ["CERT-20250801-CCC333"]


def test_instruments_csv_with_latest_certificate_and_defused_formula(client, world):
    _, rows = _csv(_get(client, f"{REPORTS}/instruments", world["owner_a"]))
    by_uiid = {r["UIID"]: r for r in rows}
    assert set(by_uiid) == {"LM-24-AAAA0001", "LM-24-AAAA0002"}
    assert by_uiid["LM-24-AAAA0001"]["Certificate"] == "Expired"
    assert by_uiid["LM-24-AAAA0002"]["Certificate"] == "Valid" and by_uiid["LM-24-AAAA0002"]["Latest certificate no."] == "CERT-20260901-AAA111"
    assert by_uiid["LM-24-AAAA0002"]["Manufacturer"].startswith("'=cmd")      # shown as text, never run as a formula
    assert by_uiid["LM-24-AAAA0001"]["Address"] == "Main Road"
    _, rows = _csv(_get(client, f"{REPORTS}/instruments", world["admin"], q="SER-300"))
    assert [r["Certificate"] for r in rows] == ["Expiring soon"]


def test_instruments_report_is_not_for_officers(client, world):
    assert _get(client, f"{REPORTS}/instruments", world["lmo"]).status_code == 403


def test_instruments_report_marks_never_verified(client, world):
    world["db"]["certificates"].delete_many({})
    _, rows = _csv(_get(client, f"{REPORTS}/instruments", world["owner_a"]))
    assert {r["Certificate"] for r in rows} == {"Not yet verified"}


# ------------------------------------------------------------------ reports: PDF, limit, audit trail

@pytest.mark.parametrize("kind", ["applications", "certificates", "instruments"])
def test_pdf_reports(client, world, kind):
    r = _get(client, f"{REPORTS}/{kind}", world["admin"], format="pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert re.fullmatch(rf'attachment; filename="maapsetu-{kind}-\d{{8}}-\d{{4}}\.pdf"', r.headers["content-disposition"])
    assert r.content.startswith(b"%PDF-")


def test_pdf_report_with_no_rows_and_awkward_text(client, world):
    assert _get(client, f"{REPORTS}/applications", world["admin"], format="pdf", q="nothing-like-this").content.startswith(b"%PDF-")
    assert _get(client, f"{REPORTS}/applications", world["admin"], format="pdf", q="<b>&").content.startswith(b"%PDF-")


def test_report_limit_keeps_the_newest_rows_and_says_so(client, world, monkeypatch):
    monkeypatch.setattr(world["reports"], "REPORT_MAX_ROWS", 2)
    r = _get(client, f"{REPORTS}/applications", world["admin"])
    assert (r.headers["x-report-rows"], r.headers["x-report-total"], r.headers["x-report-truncated"]) == ("2", "4", "true")
    _, rows = _csv(r)
    assert [x["Application ID"] for x in rows] == [str(world["app1"]), str(world["app3"])]
    assert "x-report-total" in r.headers["access-control-expose-headers"].lower()


def test_report_validation(client, world):
    assert _get(client, f"{REPORTS}/applications", world["admin"], format="xlsx").status_code == 422
    assert _get(client, f"{REPORTS}/applications", world["admin"], date_from="2026-10-18", date_to="2026-10-17").status_code == 400
    assert _get(client, f"{REPORTS}/certificates", world["admin"], instrument_type="Flying Carpet").status_code == 400
    assert client.get(f"{REPORTS}/applications").status_code in (401, 403)


def test_every_download_is_audited(client, world):
    _get(client, f"{REPORTS}/certificates", world["owner_a"], format="pdf")
    _get(client, f"{REPORTS}/applications", world["admin"])
    records = list(world["db"]["audit_logs"].find({"event": "report_exported"}).sort("created_at", 1))
    assert [(r["email"], r["role"], r["outcome"]) for r in records] == [
        ("a@example.com", "owner", "success"), ("admin@example.com", "admin", "success"),
    ]
    assert records[0]["detail"].startswith("certificates pdf rows=2")
    assert records[1]["detail"].startswith("applications csv rows=4")


def test_a_refused_report_is_not_audited(client, world):
    _get(client, f"{REPORTS}/instruments", world["lmo"])
    _get(client, f"{REPORTS}/applications", world["admin"], date_from="2026-10-18", date_to="2026-10-17")
    assert world["db"]["audit_logs"].count_documents({"event": "report_exported"}) == 0


def test_audit_log_report_is_admin_only_and_uses_the_viewer_filters(client, world):
    db = world["db"]
    now = datetime.now(timezone.utc)
    db["audit_logs"].insert_many([
        {"event": "login_failed", "outcome": "failure", "email": "x@example.com", "role": "owner", "ip": "1.2.3.4",
         "detail": "bad_password", "created_at": now},
        {"event": "login_success", "outcome": "success", "email": "y@example.com", "role": "owner", "ip": "1.2.3.5",
         "created_at": now},
    ])
    assert _get(client, f"{REPORTS}/audit-logs", world["owner_a"]).status_code == 403
    assert _get(client, f"{REPORTS}/audit-logs", world["lmo"]).status_code == 403
    header, rows = _csv(_get(client, f"{REPORTS}/audit-logs", world["admin"], outcome="failure"))
    assert header[:3] == ["Time (IST)", "Event", "Outcome"]
    assert [(r["Event"], r["Account"], r["IP address"], r["Detail"]) for r in rows] == [
        ("Login failed", "x@example.com", "1.2.3.4", "bad_password"),
    ]
    _, rows = _csv(_get(client, f"{REPORTS}/audit-logs", world["admin"], search="Y@EXAMPLE"))
    assert [r["Event"] for r in rows] == ["Login success"]
    assert _get(client, f"{REPORTS}/audit-logs", world["admin"], event="not_an_event").status_code == 400
    assert _get(client, f"{REPORTS}/audit-logs", world["admin"], date_from="2026-10-18", date_to="2026-10-17").status_code == 400
    assert _get(client, f"{REPORTS}/audit-logs", world["admin"], format="pdf").content.startswith(b"%PDF-")
