from fastapi import APIRouter, HTTPException

from app.config.db import states_col, districts_col
from app.models.geo import StateOut, DistrictOut

router = APIRouter(prefix="/api/v1/geo", tags=["geo"])


@router.get("/states", response_model=list[StateOut])
def list_states():
    docs = states_col.find().sort("name", 1)
    return [StateOut(**d) for d in docs]


@router.get("/states/{state_code}/districts", response_model=list[DistrictOut])
def list_districts(state_code: str):
    state_code = state_code.upper()
    if not states_col.find_one({"code": state_code}):
        raise HTTPException(status_code=404, detail="Unknown state_code")
    docs = districts_col.find({"state_code": state_code}).sort("name", 1)
    return [DistrictOut(**d) for d in docs]
