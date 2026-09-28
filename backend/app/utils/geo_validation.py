from typing import Optional
from fastapi import HTTPException

from app.config.db import states_col, districts_col


def validate_state_district(state_code: str, district_code: Optional[str] = None) -> None:
    """Reject unknown state/district codes at write time — the reference
    collections (seeded by seed_geo.py) are the source of truth, not the
    client. Without this, a typo'd code would silently break jurisdiction
    routing downstream (instrument -> application -> officer queue).

    Shared by routers/instruments.py (instrument location) and
    routers/admin_users.py (officer jurisdiction) so the check can't drift
    between the two call sites the way two separate copies eventually do.

    district_code=None only checks the state — the valid shape for a
    state-level jurisdiction (e.g. a GATC/state-controller officer
    account). Pass the code to also check it belongs to that state.
    """
    if not states_col.find_one({"code": state_code}):
        raise HTTPException(status_code=400, detail=f"Unknown state_code '{state_code}'")

    if district_code is not None:
        if not districts_col.find_one({"code": district_code, "state_code": state_code}):
            raise HTTPException(
                status_code=400, detail=f"Unknown district_code '{district_code}' for state '{state_code}'"
            )
