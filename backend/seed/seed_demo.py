"""
backend/seed/seed_demo.py  --  realistic demo data for the SIH26036 video.

Covers 4 states x 3-4 districts (15 districts):
  West Bengal  : Murshidabad, Kolkata, Howrah, North 24 Parganas
  Maharashtra  : Mumbai, Pune, Nagpur, Nashik
  Karnataka    : Bengaluru Urban, Mysuru, Dharwad, Belagavi
  Tamil Nadu   : Chennai, Coimbatore, Madurai

  * 4 GATC officers   - one per STATE   (state-level jurisdiction)
  * 15 LMO officers   - one per DISTRICT (district-level jurisdiction)
  * 20 owners, 39 instruments, applications / inspections / certificates
  * Exactly ONE near-expiry and ONE expired certificate, both on the demo owner

Run from backend/ (venv active, .env loaded):

    python -m seed.seed_demo                 # create / refresh demo data
    python -m seed.seed_demo --code          # print current officer login code (2-step)
    python -m seed.seed_demo --remove        # delete only the demo data

Set DEMO_EMAIL in .env (or the shell) to YOUR real inbox: the demo owner gets that
address, so the expiry emails arrive in your mailbox while recording.

Safe to re-run: it only deletes documents it created itself (marked demo_seed=True).
"""
import argparse
import hashlib
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bson import ObjectId  # noqa: E402

PASSWORD = "Demo@2026!"                       # every demo account
TOTP_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"  # shared by all demo officers (base32)
DEMO_EMAIL = os.getenv("DEMO_EMAIL", "demo.owner@example.com").strip().lower()
OFFICER_DOMAIN = "legalmetrology.gov.in"

# ---------------------------------------------------------------- geography
# state_code: (name, [(district_code, district_name, city used in addresses)])
GEO = {
    "WB": ("West Bengal", [("319", "Murshidabad", "Baharampur"), ("315", "Kolkata", "Kolkata"),
                           ("313", "Howrah", "Howrah"), ("303", "North 24 Parganas", "Barasat")]),
    "MH": ("Maharashtra", [("482", "Mumbai", "Mumbai"), ("490", "Pune", "Pune"),
                           ("484", "Nagpur", "Nagpur"), ("487", "Nashik", "Nashik")]),
    "KA": ("Karnataka", [("525", "Bengaluru Urban", "Bengaluru"), ("545", "Mysuru", "Mysuru"),
                         ("536", "Dharwad", "Hubballi"), ("527", "Belagavi", "Belagavi")]),
    "TN": ("Tamil Nadu", [("568", "Chennai", "Chennai"), ("569", "Coimbatore", "Coimbatore"),
                          ("578", "Madurai", "Madurai")]),
}

# state -> (GATC officer name, phone)
GATC = {
    "WB": ("Sanjay Ghosh", "9830011101"),
    "MH": ("Meenal Deshpande", "9820011102"),
    "KA": ("Ramesh Hegde", "9880011103"),
    "TN": ("Lakshmi Venkatesan", "9840011104"),
}

# district_code -> LMO officer (name, phone)
LMO = {
    "319": ("Anjali Roy", "9433022201"), "315": ("Subrata Chakraborty", "9830022202"),
    "313": ("Pradip Mukherjee", "9831022203"), "303": ("Moumita Sen", "9830022204"),
    "482": ("Rahul Kamble", "9821022205"), "490": ("Neha Joshi", "9822022206"),
    "484": ("Sandeep Wankhede", "9823022207"), "487": ("Kavita Shinde", "9824022208"),
    "525": ("Suresh Naik", "9886022209"), "545": ("Divya Prakash", "9845022210"),
    "536": ("Mahantesh Kulkarni", "9448022211"), "527": ("Anand Desai", "9449022212"),
    "568": ("Karthik Rajan", "9841022213"), "569": ("Priya Natarajan", "9842022214"),
    "578": ("Senthil Kumar", "9843022215"),
}

# ------------------------------------------------------------------- owners
# key: (name, email, org_name, phone, state, district)
OWNERS = {
    "demo": ("Subhajit Saha", DEMO_EMAIL, "Saha Traders & Weighing Co.", "9733001001", "WB", "319"),
    "wb2":  ("Rina Ghosh", "rina.ghosh@demo-maapsetu.in", "Ghosh Petrol Pump", "9733001002", "WB", "319"),
    "wb3":  ("Debashis Banerjee", "debashis.banerjee@demo-maapsetu.in", "Banerjee Jewellers", "9830001003", "WB", "315"),
    "wb4":  ("Sunita Agarwal", "sunita.agarwal@demo-maapsetu.in", "Agarwal Fuel Station", "9830001004", "WB", "315"),
    "wb5":  ("Mohammad Rafique", "m.rafique@demo-maapsetu.in", "Rafique Steel Works", "9831001005", "WB", "313"),
    "wb6":  ("Tapas Dutta", "tapas.dutta@demo-maapsetu.in", "Dutta Rice Mill", "9830001006", "WB", "303"),
    "mh1":  ("Rajesh Patil", "rajesh.patil@demo-maapsetu.in", "Patil Gold & Diamonds", "9820001007", "MH", "482"),
    "mh2":  ("Sneha Kulkarni", "sneha.kulkarni@demo-maapsetu.in", "Kulkarni Dairy Products", "9822001008", "MH", "490"),
    "mh3":  ("Vikram Jadhav", "vikram.jadhav@demo-maapsetu.in", "Jadhav Fuel Point", "9822001009", "MH", "490"),
    "mh4":  ("Amit Deshmukh", "amit.deshmukh@demo-maapsetu.in", "Deshmukh Oil Mill", "9823001010", "MH", "484"),
    "mh5":  ("Prakash Pawar", "prakash.pawar@demo-maapsetu.in", "Pawar Weighbridge Services", "9824001011", "MH", "487"),
    "ka1":  ("Lakshmi Narayan", "lakshmi.narayan@demo-maapsetu.in", "Sri Lakshmi Provisions", "9886001012", "KA", "525"),
    "ka2":  ("Karthik Reddy", "karthik.reddy@demo-maapsetu.in", "Reddy Auto Fuels", "9845001013", "KA", "525"),
    "ka3":  ("Shivakumar Gowda", "shivakumar.gowda@demo-maapsetu.in", "Gowda Sugar Traders", "9845001014", "KA", "545"),
    "ka4":  ("Basavaraj Hiremath", "basavaraj.hiremath@demo-maapsetu.in", "Hiremath Grain Merchants", "9448001015", "KA", "536"),
    "ka5":  ("Sunil Patil", "sunil.patil@demo-maapsetu.in", "Patil Jaggery Works", "9449001016", "KA", "527"),
    "tn1":  ("Murugan Selvam", "murugan.selvam@demo-maapsetu.in", "Selvam Textiles", "9841001017", "TN", "568"),
    "tn2":  ("Fatima Beevi", "fatima.beevi@demo-maapsetu.in", "Beevi Medical Stores", "9841001018", "TN", "568"),
    "tn3":  ("Ramesh Subramaniam", "ramesh.subramaniam@demo-maapsetu.in", "Sri Ganapathy Weighbridge", "9842001019", "TN", "569"),
    "tn4":  ("Karthikeyan Pandian", "karthikeyan.pandian@demo-maapsetu.in", "Pandian Jasmine Traders", "9843001020", "TN", "578"),
}

# --------------------------------------------------------------- instruments
# (owner, type, manufacturer, model, capacity_number, serial, address, scenario)
# scenario:
#   valid:N[:G]   certified, N days left (N >= 45 so no reminder is triggered)
#   near          certified, 6 days left   -> expiry reminder + notification
#   expired       certificate lapsed 3 days ago -> expired notification
#   submitted     waiting in the officer queue (unassigned)
#   scheduled[:G] claimed by the officer, ready to inspect
#   rejected[:G]  inspection failed
#   unapplied     registered, no application yet (use this for the live demo flow)
# ":G" = handled by the state GATC officer instead of the district LMO.
I = [
    # --- West Bengal / Murshidabad (demo owner: the star of the video)
    ("demo", "Electronic Weighing Machine", "Essae-Teraoka", "DS-252", "30", "ET25-884102", "Station Road, Khagra, Baharampur", "valid:210"),
    ("demo", "Platform Scale", "Libra Scales", "PS-500", "500", "LB22-310477", "Gorabazar Market, Baharampur", "valid:140:G"),
    ("demo", "Beam Scale", "Atlas Scales", "BS-20", "20", "AT24-120956", "Cossimbazar Road, Baharampur", "near"),
    ("demo", "Non-Automatic Weighing Instrument", "Phoenix Scales", "NAWI-15", "15", "PH23-554301", "Lalbagh Bazar, Murshidabad", "expired"),
    ("demo", "Electronic Weighing Machine", "Contech", "CAS-60", "60", "CT26-009871", "Station Road, Khagra, Baharampur", "unapplied"),
    ("demo", "Weights", "Mangal Weights", "MW-1KG", "1", "MG26-770120", "Gorabazar Market, Baharampur", "submitted"),
    ("wb2", "Fuel Dispensing Unit", "Gilbarco Veeder-Root", "Encore 300", "40", "GV24-660318", "NH-34, Berhampore", "valid:260"),
    ("wb2", "Fuel Dispensing Unit", "Tokheim", "Quantium 510", "40", "TK25-120874", "NH-34, Berhampore", "scheduled"),
    # --- West Bengal / Kolkata
    ("wb3", "Electronic Weighing Machine", "Essae-Teraoka", "DS-415", "6", "ET25-441290", "Burrabazar, Kolkata", "valid:300"),
    ("wb3", "Weights", "Mangal Weights", "MW-500G", "0.5", "MG24-300418", "Burrabazar, Kolkata", "valid:95"),
    ("wb4", "Fuel Dispensing Unit", "Tatsuno India", "Sunny Sigma", "40", "TA24-880231", "Salt Lake Sector V, Kolkata", "valid:180"),
    ("wb4", "Fuel Dispensing Unit", "Gilbarco Veeder-Root", "Encore 400", "40", "GV25-452019", "Salt Lake Sector V, Kolkata", "submitted"),
    # --- West Bengal / Howrah
    ("wb5", "Platform Scale", "Avery Weigh-Tronix", "ZM-1000", "1000", "AW23-775402", "Liluah Industrial Area, Howrah", "valid:70"),
    ("wb5", "Load Cell", "Sensortronics", "LC-5T", "5000", "SN25-118830", "Liluah Industrial Area, Howrah", "rejected"),
    # --- West Bengal / North 24 Parganas
    ("wb6", "Platform Scale", "Libra Scales", "PS-300", "300", "LB24-902215", "Jessore Road, Barasat", "valid:230"),
    # --- Maharashtra / Mumbai
    ("mh1", "Electronic Weighing Machine", "Essae-Teraoka", "DS-415", "6", "ET25-661042", "Zaveri Bazaar, Mumbai", "valid:250"),
    ("mh1", "Weights", "Mangal Weights", "MW-100G", "0.1", "MG25-450871", "Zaveri Bazaar, Mumbai", "valid:120"),
    # --- Maharashtra / Pune
    ("mh2", "Water Meter", "Kranti Meters", "KM-15", "1.5", "KR25-330196", "Hadapsar Industrial Estate, Pune", "valid:190"),
    ("mh3", "Fuel Dispensing Unit", "Gilbarco Veeder-Root", "Encore 300", "40", "GV24-770654", "Wakad Road, Pune", "valid:160:G"),
    ("mh3", "Fuel Dispensing Unit", "Tokheim", "Quantium 510", "40", "TK25-884011", "Wakad Road, Pune", "scheduled:G"),
    # --- Maharashtra / Nagpur
    ("mh4", "Flow Meter", "Forbes Marshall", "FM-50", "50", "FM24-206537", "Kamptee Road, Nagpur", "valid:85"),
    # --- Maharashtra / Nashik
    ("mh5", "Automatic Rail Weighbridge", "Essae-Teraoka", "ARW-150", "150", "ET23-100842", "Ambad MIDC, Nashik", "valid:310:G"),
    ("mh5", "Platform Scale", "Avery Weigh-Tronix", "ZM-500", "500", "AW25-662310", "Ambad MIDC, Nashik", "submitted"),
    # --- Karnataka / Bengaluru Urban
    ("ka1", "Electronic Weighing Machine", "Essae-Teraoka", "DS-252", "30", "ET24-550198", "Chickpet, Bengaluru", "valid:200"),
    ("ka2", "Fuel Dispensing Unit", "Gilbarco Veeder-Root", "Encore 700", "40", "GV25-119204", "Whitefield Main Road, Bengaluru", "valid:150:G"),
    ("ka2", "Energy Meter", "Secure Meters", "SM-3PH", "10", "SC25-740215", "Whitefield Main Road, Bengaluru", "scheduled"),
    # --- Karnataka / Mysuru
    ("ka3", "Platform Scale", "Libra Scales", "PS-500", "500", "LB25-410982", "Devaraja Market, Mysuru", "valid:110"),
    # --- Karnataka / Dharwad (Hubballi)
    ("ka4", "Platform Scale", "Avery Weigh-Tronix", "ZM-1000", "1000", "AW24-884532", "APMC Yard, Hubballi", "valid:280"),
    ("ka4", "Load Cell", "Sensortronics", "LC-10T", "10000", "SN25-229871", "APMC Yard, Hubballi", "submitted"),
    # --- Karnataka / Belagavi
    ("ka5", "Beam Scale", "Atlas Scales", "BS-20", "20", "AT25-330412", "Market Yard, Gokak, Belagavi", "valid:60"),
    # --- Tamil Nadu / Chennai
    ("tn1", "Tape Measure", "Freemans Measures", "FT-30", "30", "FR25-120077", "T. Nagar, Chennai", "valid:130"),
    ("tn2", "Clinical Thermometer", "Hicks Thermometers", "HT-DG1", "42", "HK25-884120", "Purasawalkam, Chennai", "valid:240"),
    ("tn2", "Electronic Weighing Machine", "Contech", "CAS-30", "30", "CT25-554310", "Purasawalkam, Chennai", "rejected:G"),
    # --- Tamil Nadu / Coimbatore
    ("tn3", "Automatic Rail Weighbridge", "Essae-Teraoka", "ARW-100", "100", "ET24-660903", "Ganapathy, Coimbatore", "valid:175"),
    # --- Tamil Nadu / Madurai
    ("tn4", "Electronic Weighing Machine", "Essae-Teraoka", "DS-252", "30", "ET25-774013", "Mattuthavani Market, Madurai", "valid:220"),
    ("tn4", "Counter Machine", "Pennant Counters", "PC-500", "500", "PN25-203318", "Mattuthavani Market, Madurai", "scheduled"),
]

UNITS = {
    "Electronic Weighing Machine": "kg", "Fuel Dispensing Unit": "L/min", "Platform Scale": "kg",
    "Water Meter": "m³", "Clinical Thermometer": "°C", "Automatic Rail Weighbridge": "tonnes",
    "Tape Measure": "m", "Non-Automatic Weighing Instrument": "kg", "Load Cell": "kg",
    "Beam Scale": "kg", "Counter Machine": "pcs/min", "Weights": "kg", "Gas Meter": "m³/h",
    "Energy Meter": "kWh", "Moisture Meter": "%", "Speed Meter": "km/h",
    "Breath Analyser": "mg/L", "Flow Meter": "L/min",
}

PASS_NOTES = [
    "Verified against standard weights traceable to the state secondary standard. Errors within MPE. Seal affixed.",
    "Performance checked at 10%, 50% and 100% of capacity. Repeatability and eccentricity within limits. Stamped.",
    "Instrument inspected on site. Dimensions, markings and sealing provisions comply with the Rules. Stamped.",
]
FAIL_NOTES = [
    "Error at 50% load exceeds the maximum permissible error. Owner advised to repair and re-apply.",
    "Sealing provisions tampered and calibration drift found at full capacity. Re-verification required.",
]


def _hash(*parts) -> str:
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest().upper()


def _officer_email(name: str) -> str:
    return f"{name.lower().replace(' ', '.')}@{OFFICER_DOMAIN}".replace("..", ".")


def build_plan(now: datetime) -> dict:
    """Pure data - no DB access. Returns everything that will be inserted."""
    users, instruments = [], []

    for sc, (name, phone) in GATC.items():
        users.append(dict(key=f"gatc_{sc}", name=f"{name}", email=_officer_email(name), role="gatc",
                          org_type="GATC", org_name=f"{GEO[sc][0]} Government Approved Test Centre",
                          contact=phone, jurisdiction={"state_code": sc}))
    for sc, (_, districts) in GEO.items():
        for dc, dname, _city in districts:
            name, phone = LMO[dc]
            users.append(dict(key=f"lmo_{dc}", name=name, email=_officer_email(name), role="lmo",
                              org_type="LMO", org_name=f"Legal Metrology Office, {dname}",
                              contact=phone, jurisdiction={"state_code": sc, "district_code": dc}))
    for k, (name, email, org, phone, sc, dc) in OWNERS.items():
        users.append(dict(key=f"owner_{k}", name=name, email=email, role="owner", org_type=None,
                          org_name=org, contact=phone, jurisdiction=None))

    for n, (ok, typ, mfr, model, cap, serial, addr, scen) in enumerate(I):
        sc, dc = OWNERS[ok][4], OWNERS[ok][5]
        parts = scen.split(":")
        kind = parts[0]
        by_gatc = parts[-1] == "G"
        days_left = {"near": 6, "expired": -3}.get(kind, int(parts[1]) if kind == "valid" else None)
        instruments.append(dict(
            n=n, owner=f"owner_{ok}", type=typ, manufacturer=mfr, model=model,
            capacity=f"{cap} {UNITS[typ]}", serial_no=serial,
            location={"state_code": sc, "district_code": dc, "address_line": addr},
            kind=kind, days_left=days_left,
            officer=(f"gatc_{sc}" if by_gatc else f"lmo_{dc}"),
        ))
    return {"users": users, "instruments": instruments}


# ------------------------------------------------------------------ DB part
def timeline(inst: dict, now: datetime) -> dict:
    """submitted/inspected/issued timestamps for one instrument, all relative to now."""
    kind = inst["kind"]
    if kind in ("valid", "near", "expired"):
        valid_until = now + timedelta(days=inst["days_left"])
        issued = valid_until - timedelta(days=365)
        inspected = issued - timedelta(hours=2)
        scheduled = inspected - timedelta(days=2)
        submitted = scheduled - timedelta(days=3)
        return dict(submitted=submitted, scheduled=scheduled, inspected=inspected, issued=issued, valid_until=valid_until)
    if kind == "rejected":
        inspected = now - timedelta(days=9 + inst["n"] % 5)
        return dict(submitted=inspected - timedelta(days=5), scheduled=inspected - timedelta(days=2), inspected=inspected)
    if kind == "scheduled":
        return dict(submitted=now - timedelta(days=3), scheduled=now - timedelta(days=1))
    if kind == "submitted":
        return dict(submitted=now - timedelta(days=1, hours=inst["n"] % 7))
    return {}


def remove_demo(cols):
    users_col, instruments_col, applications_col, inspections_col, certificates_col, alerts_col, email_log_col = cols
    ids = [u["_id"] for u in users_col.find({"demo_seed": True}, {"_id": 1})]
    cert_ids = [c["_id"] for c in certificates_col.find({"demo_seed": True}, {"_id": 1})]
    certificates_col.delete_many({"demo_seed": True})
    inspections_col.delete_many({"demo_seed": True})
    applications_col.delete_many({"demo_seed": True})
    instruments_col.delete_many({"demo_seed": True})
    alerts_col.delete_many({"certificate_id": {"$in": cert_ids}})
    for cid in cert_ids:  # email dedupe keys, so the reminder mails can be sent again
        email_log_col.delete_many({"_id": {"$regex": f"^(expiry_reminder|certificate_expired):{cid}"}})
    users_col.delete_many({"_id": {"$in": ids}})
    return len(ids)


def run():
    from app.config.db import (users_col, instruments_col, applications_col, inspections_col,
                               certificates_col, alerts_col, email_log_col, states_col, districts_col,
                               init_indexes)
    from app.config.geo_data import STATES_UTS
    from app.services.uiid_generator import generate_uiid
    from app.utils.mfa import encrypt_secret
    from app.utils.security import hash_password

    cols = (users_col, instruments_col, applications_col, inspections_col, certificates_col, alerts_col, email_log_col)
    try:
        init_indexes()
    except Exception:
        pass

    now = datetime.now(timezone.utc).replace(microsecond=0)
    removed = remove_demo(cols)
    if removed:
        print(f"Removed {removed} users from a previous demo seed.")

    # Reference data for the states/districts used here (upsert, harmless if already present).
    for sc, (sname, districts) in GEO.items():
        st = next((s for s in STATES_UTS if s["code"] == sc), {"code": sc, "name": sname, "type": "state"})
        states_col.update_one({"code": sc}, {"$set": st}, upsert=True)
        for dc, dname, _ in districts:
            districts_col.update_one({"state_code": sc, "code": dc},
                                     {"$set": {"code": dc, "name": dname, "state_code": sc}}, upsert=True)

    clash = users_col.find_one({"email": {"$in": [o[1] for o in OWNERS.values()]}, "demo_seed": {"$ne": True}})
    if clash:
        print(f"!! {clash['email']} already exists as a non-demo account. "
              f"Set DEMO_EMAIL to a different address (or delete that account) and re-run.")
        sys.exit(1)

    plan = build_plan(now)
    pw_hash = hash_password(PASSWORD)
    mfa_secret = encrypt_secret(TOTP_SECRET)

    uid = {}
    for u in plan["users"]:
        oid = ObjectId()
        uid[u["key"]] = oid
        doc = {
            "_id": oid, "demo_seed": True, "name": u["name"], "email": u["email"], "password": pw_hash,
            "role": u["role"], "status": "active", "org_type": u["org_type"], "org_name": u["org_name"],
            "contact": u["contact"], "jurisdiction": u["jurisdiction"],
            "is_email_verified": True, "is_phone_verified": True,
            "must_change_password": False, "token_version": 0, "failed_login_attempts": 0,
            "created_at": now - timedelta(days=400),
        }
        if u["role"] in ("lmo", "gatc"):
            # Pre-enrolled two-step verification, so officers log in without the setup screen.
            doc.update(mfa_enabled=True, mfa_secret_enc=mfa_secret, mfa_enabled_at=now,
                       mfa_last_step=0, mfa_recovery_hashes=[])
        users_col.insert_one(doc)

    # Optional: real PDFs for the certificates (needs reportlab + qrcode, both in requirements.txt).
    pdf_tools = None
    try:
        from app.services import cert_generator as cg
        from app.config.settings import FRONTEND_VERIFY_URL
        pdf_tools = (cg, FRONTEND_VERIFY_URL)
    except Exception as exc:  # pragma: no cover
        print(f"(certificate PDFs skipped: {exc})")

    counts = dict(instruments=0, applications=0, inspections=0, certificates=0)
    for inst in plan["instruments"]:
        t = timeline(inst, now)
        kind = inst["kind"]
        owner_oid = uid[inst["owner"]]
        instrument_doc = {
            "_id": ObjectId(), "demo_seed": True, "owner_id": owner_oid, "type": inst["type"],
            "manufacturer": inst["manufacturer"], "model": inst["model"], "capacity": inst["capacity"],
            "serial_no": inst["serial_no"], "uiid": generate_uiid(), "location": inst["location"],
        }
        instruments_col.insert_one(instrument_doc)
        counts["instruments"] += 1
        if kind == "unapplied":
            continue

        officer_oid = uid[inst["officer"]]
        status = {"valid": "certified", "near": "expiring", "expired": "expired"}.get(kind, kind)
        steps = [(None, "submitted", t["submitted"], owner_oid, "application submitted")]
        if kind != "submitted":
            steps.append(("submitted", "scheduled", t["scheduled"], officer_oid, "claimed by officer, inspection scheduled"))
        if kind in ("valid", "near", "expired", "rejected"):
            result_status = "rejected" if kind == "rejected" else "certified"
            steps.append(("scheduled", "inspected", t["inspected"], officer_oid, None))
            steps.append(("inspected", result_status, t["inspected"] + timedelta(minutes=2), officer_oid,
                          f"inspection result: {'fail' if kind == 'rejected' else 'pass'}"))
        if kind == "near":
            steps.append(("certified", "expiring", now - timedelta(hours=1), None, "certificate expires within 30 days"))
        if kind == "expired":
            steps.append(("certified", "expiring", t["valid_until"] - timedelta(days=30), None, "certificate expires within 30 days"))
            steps.append(("expiring", "expired", t["valid_until"], None, "certificate expired"))
        history = [{"from": f, "to": to, "at": at, "changed_by": by, "reason": why} for f, to, at, by, why in steps]

        app_oid = ObjectId()
        applications_col.insert_one({
            "_id": app_oid, "demo_seed": True, "instrument_id": instrument_doc["_id"], "owner_id": owner_oid,
            "status": status, "assigned_officer_id": None if kind == "submitted" else officer_oid,
            "submitted_at": t["submitted"], "state_code": inst["location"]["state_code"],
            "district_code": inst["location"]["district_code"], "history": history,
        })
        counts["applications"] += 1
        if kind in ("submitted", "scheduled"):
            continue

        failed = kind == "rejected"
        insp_doc = {
            "_id": ObjectId(), "demo_seed": True, "application_id": app_oid, "officer_id": officer_oid,
            "observations": (FAIL_NOTES if failed else PASS_NOTES)[inst["n"] % (2 if failed else 3)],
            "result": "fail" if failed else "pass", "photos": [], "inspected_at": t["inspected"],
        }
        inspections_col.insert_one(insp_doc)
        counts["inspections"] += 1
        if failed:
            continue

        cert_no = f"CERT-{t['issued']:%Y%m%d}-{_hash(instrument_doc['uiid'])[:6]}"
        cert_doc = {
            "_id": cert_no, "demo_seed": True, "inspection_id": insp_doc["_id"], "application_id": app_oid,
            "instrument_id": instrument_doc["_id"], "cert_no": cert_no, "qr_url": None, "pdf_url": None,
            "issued_at": t["issued"], "valid_until": t["valid_until"],
        }
        if pdf_tools:
            try:
                from bson import Binary
                cg, verify_base = pdf_tools
                verify_url = f"{verify_base.rstrip('/')}/{cert_no}"
                owner_doc = users_col.find_one({"_id": owner_oid})
                pdf = cg._generate_pdf_bytes(cert_no, instrument_doc, insp_doc, {"_id": app_oid}, owner_doc,
                                             t["valid_until"], t["issued"], cg._make_qr_png(verify_url), verify_url)
                cert_doc["pdf_data"] = Binary(pdf)
            except Exception as exc:
                print(f"(no PDF for {cert_no}: {exc})")
                pdf_tools = None
        certificates_col.insert_one(cert_doc)
        counts["certificates"] += 1

    print()
    print(f"Done. {len(plan['users'])} users, {counts['instruments']} instruments, "
          f"{counts['applications']} applications, {counts['inspections']} inspections, "
          f"{counts['certificates']} certificates.")
    print_logins()


def print_logins():
    print(f"\nPassword for EVERY demo account: {PASSWORD}")
    print(f"Demo owner (expiry emails go here): {DEMO_EMAIL}")
    print("Officers need a 2-step code: run  python -m seed.seed_demo --code\n")
    print("GATC (state level):")
    for sc, (name, _) in GATC.items():
        print(f"  {GEO[sc][0]:<12} {_officer_email(name)}")
    print("LMO (district level):")
    for sc, (_, districts) in GEO.items():
        for dc, dname, _ in districts:
            print(f"  {GEO[sc][0]:<12} {dname:<18} {_officer_email(LMO[dc][0])}")


def print_code():
    from app.utils.totp import totp_at
    import time
    print(f"Current officer 2-step code: {totp_at(TOTP_SECRET)}  (changes in {30 - int(time.time()) % 30}s)")
    print(f"Or add this key to an authenticator app: {TOTP_SECRET}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--remove", action="store_true", help="delete the demo data only")
    ap.add_argument("--code", action="store_true", help="print the current officer 2-step code")
    args = ap.parse_args()
    if args.code:
        print_code()
    elif args.remove:
        from app.config.db import (users_col, instruments_col, applications_col, inspections_col,
                                   certificates_col, alerts_col, email_log_col)
        n = remove_demo((users_col, instruments_col, applications_col, inspections_col,
                         certificates_col, alerts_col, email_log_col))
        print(f"Removed demo data ({n} users and everything they own).")
    else:
        run()
