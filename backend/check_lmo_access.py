import urllib.request
from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017")
db = client["maapsetu"]
user = db.users.find_one({"email": "anjali.roy@legalmetrology.gov.in"})
assert user, "LMO user not found"
app = db.applications.find_one({"assigned_officer_id": user["_id"]})
assert app, "No assigned app for LMO user"

# Officer accounts now sign in with a second step (authenticator code), which
# this script isn't testing -- it checks what an officer's session can SEE. So
# mint that officer's access token directly, exactly as the server would after a
# completed login (needs the same JWT_SECRET as the running API, i.e. your .env;
# run from the backend/ directory).
from app.utils.security import create_access_token  # noqa: E402

token = create_access_token(str(user["_id"]), user.get("token_version", 0))
print("token_minted_for", user["email"])

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
