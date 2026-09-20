"""
Seeds the `states` collection from app/config/geo_data.py, and the
`districts` collection from a CSV if one is provided.

States/UTs (36 total) are hardcoded in geo_data.py because that list is
genuinely stable — it's only changed twice in the country's history and
both times were significant enough to make national news. Districts are a
different story: India currently has 750+ districts and new ones get
carved out of existing ones periodically (this happens at the state level,
often without much national coverage), so district data is NOT hardcoded
here. Instead:

  1. Download the authoritative district list from India's Local
     Government Directory (LGD): https://lgdirectory.gov.in/
     (or data.gov.in's mirror of the same dataset)
  2. Save it as backend/seed/districts.csv with columns:
         code,name,state_code
     (state_code must match a code in geo_data.STATES_UTS)
  3. Re-run this script any time you refresh that file — it's an upsert,
     safe to run repeatedly.

Without that file, this script still seeds all 36 states/UTs, which is
enough to get the state-level dropdown and jurisdiction scoping working;
district-level dropdowns/scoping just won't have data yet.

Run from backend/:
    python seed_geo.py
"""

import csv
import os

from app.config.db import states_col, districts_col
from app.config.geo_data import STATES_UTS

DISTRICTS_CSV = os.path.join(os.path.dirname(__file__), "seed", "districts.csv")


def seed_states():
    for state in STATES_UTS:
        states_col.update_one({"code": state["code"]}, {"$set": state}, upsert=True)
    print(f"Seeded {len(STATES_UTS)} states/UTs.")


def seed_districts():
    if not os.path.exists(DISTRICTS_CSV):
        print(f"No {DISTRICTS_CSV} found — skipping districts. See this file's docstring.")
        return

    state_codes = {s["code"] for s in STATES_UTS}
    count = 0
    skipped = 0
    with open(DISTRICTS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["state_code"] not in state_codes:
                skipped += 1
                continue
            districts_col.update_one(
                {"state_code": row["state_code"], "code": row["code"]},
                {"$set": {"code": row["code"], "name": row["name"], "state_code": row["state_code"]}},
                upsert=True,
            )
            count += 1
    print(f"Seeded {count} districts." + (f" Skipped {skipped} rows with unknown state_code." if skipped else ""))


if __name__ == "__main__":
    seed_states()
    seed_districts()
