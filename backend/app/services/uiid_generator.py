"""
Generates the government-style unique instrument ID (UIID) referenced in
the anti-substitution design: every registered instrument gets one fixed
identity string that never changes, independent of its serial number.

Format: LM-000001, LM-000002, ...
  - "LM" = Legal Metrology (static prefix)
  - 6-digit zero-padded sequential number

Deliberately NOT encoding state/district here, since Instrument.location
is a free-text field, not a structured dropdown — guessing a 2-letter
state code out of free text would produce wrong or inconsistent codes.
If the team adds a proper `state` field later (already flagged as a nice-
to-have for the admin dashboard's location grouping too), this format can
be upgraded to LM-{STATE}-000001 by changing only the format() call below
— the counter logic itself doesn't need to change.

Uses MongoDB's atomic findAndModify (via find_one_and_update) so two
instruments registering at the exact same moment can never receive the
same number, even under concurrent requests.
"""

from pymongo import ReturnDocument
from app.config.db import counters_col

COUNTER_NAME = "instrument_uiid"


def generate_uiid() -> str:
    result = counters_col.find_one_and_update(
        {"_id": COUNTER_NAME},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    seq = result["seq"]
    return f"LM-{seq:06d}"
