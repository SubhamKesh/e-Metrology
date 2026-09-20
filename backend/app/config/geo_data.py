# Reference data only — seeded into `states_col` by scripts/seed_geo.py,
# never imported directly into request-handling code. Routers/models look
# codes up in the DB (app/routers/geo.py), the same way any other
# admin-editable reference data would be handled.
#
# 28 states + 8 union territories = 36, current as of this file's writing.
# This list HAS changed before (J&K -> J&K UT + Ladakh in 2019; Dadra &
# Nagar Haveli merged with Daman & Diu in 2020) and could change again —
# that's exactly why this lives in a seedable collection instead of a
# Literal/Enum baked into the type system. If a reorganization happens,
# update this file and re-run the seed script; no model changes needed.
#
# Codes follow the ISO 3166-2:IN convention (used by India's own Local
# Government Directory / LGD portal) so they line up with any official
# district data you load alongside this.

STATES_UTS = [
    # --- States (28) ---
    {"code": "AP", "name": "Andhra Pradesh", "type": "state"},
    {"code": "AR", "name": "Arunachal Pradesh", "type": "state"},
    {"code": "AS", "name": "Assam", "type": "state"},
    {"code": "BR", "name": "Bihar", "type": "state"},
    {"code": "CT", "name": "Chhattisgarh", "type": "state"},
    {"code": "GA", "name": "Goa", "type": "state"},
    {"code": "GJ", "name": "Gujarat", "type": "state"},
    {"code": "HR", "name": "Haryana", "type": "state"},
    {"code": "HP", "name": "Himachal Pradesh", "type": "state"},
    {"code": "JH", "name": "Jharkhand", "type": "state"},
    {"code": "KA", "name": "Karnataka", "type": "state"},
    {"code": "KL", "name": "Kerala", "type": "state"},
    {"code": "MP", "name": "Madhya Pradesh", "type": "state"},
    {"code": "MH", "name": "Maharashtra", "type": "state"},
    {"code": "MN", "name": "Manipur", "type": "state"},
    {"code": "ML", "name": "Meghalaya", "type": "state"},
    {"code": "MZ", "name": "Mizoram", "type": "state"},
    {"code": "NL", "name": "Nagaland", "type": "state"},
    {"code": "OR", "name": "Odisha", "type": "state"},
    {"code": "PB", "name": "Punjab", "type": "state"},
    {"code": "RJ", "name": "Rajasthan", "type": "state"},
    {"code": "SK", "name": "Sikkim", "type": "state"},
    {"code": "TN", "name": "Tamil Nadu", "type": "state"},
    {"code": "TG", "name": "Telangana", "type": "state"},
    {"code": "TR", "name": "Tripura", "type": "state"},
    {"code": "UP", "name": "Uttar Pradesh", "type": "state"},
    {"code": "UT", "name": "Uttarakhand", "type": "state"},
    {"code": "WB", "name": "West Bengal", "type": "state"},
    # --- Union Territories (8) ---
    {"code": "AN", "name": "Andaman and Nicobar Islands", "type": "ut"},
    {"code": "CH", "name": "Chandigarh", "type": "ut"},
    {"code": "DN", "name": "Dadra and Nagar Haveli and Daman and Diu", "type": "ut"},
    {"code": "DL", "name": "Delhi", "type": "ut"},
    {"code": "JK", "name": "Jammu and Kashmir", "type": "ut"},
    {"code": "LA", "name": "Ladakh", "type": "ut"},
    {"code": "LD", "name": "Lakshadweep", "type": "ut"},
    {"code": "PY", "name": "Puducherry", "type": "ut"},
]

STATE_CODES = {s["code"] for s in STATES_UTS}
