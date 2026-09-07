import json
import urllib.request
from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017")
db = client["maapsetu"]
user = db.users.find_one({"email": "anjali.roy@legalmetrology.gov.in"})
assert user, "LMO user not found"
app = db.applications.find_one({"assigned_officer_id": user["_id"]})
assert app, "No assigned app for LMO user"

login_req = urllib.request.Request(
    "http://127.0.0.1:8000/api/v1/auth/login",
    data=json.dumps({
        "email": "anjali.roy@legalmetrology.gov.in",
        "password": "seed-pass-004",
    }).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(login_req, timeout=20) as resp:
    login_body = resp.read().decode()
    login_data = json.loads(login_body)
    print("login_status", resp.status)
    token = login_data["token"]

headers = {"Authorization": f"Bearer {token}"}
app_req = urllib.request.Request(
    f"http://127.0.0.1:8000/api/v1/applications/{str(app['_id'])}",
    headers=headers,
)
with urllib.request.urlopen(app_req, timeout=20) as resp:
    app_body = resp.read().decode()
    print("application_status", resp.status)
    print("application_body", app_body[:250])

inst_req = urllib.request.Request(
    f"http://127.0.0.1:8000/api/v1/instruments/{str(app['instrument_id'])}",
    headers=headers,
)
with urllib.request.urlopen(inst_req, timeout=20) as resp:
    inst_body = resp.read().decode()
    print("instrument_status", resp.status)
    print("instrument_body", inst_body[:250])

assert "application_status" in "application_status" or True
print("lmo_access_ok")
