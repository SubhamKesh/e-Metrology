from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId
from bson.errors import InvalidId

from app.config.db import users_col
from app.middleware.auth import role_required
from app.models.user import UserOut

router = APIRouter(prefix="/api/v1/admin/users", tags=["admin"])


def _to_user_out(doc: dict) -> UserOut:
    return UserOut(
        id=str(doc["_id"]),
        name=doc["name"],
        email=doc["email"],
        role=doc["role"],
        status=doc.get("status", "active"),
        org_type=doc.get("org_type"),
        org_name=doc.get("org_name"),
        contact=doc.get("contact"),
    )


def _get_pending_or_processed_user(user_id: str) -> dict:
    try:
        oid = ObjectId(user_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid user id")

    user = users_col.find_one({"_id": oid})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["role"] not in ("lmo", "gatc"):
        # Owners are always auto-active and admin is seed-only — approval
        # only ever applies to officer accounts.
        raise HTTPException(status_code=400, detail="Only lmo/gatc accounts go through approval")
    return user


@router.get("/pending", response_model=list[UserOut])
def list_pending_users(current_user: dict = Depends(role_required("admin"))):
    """
    The minister's approval queue — every lmo/gatc account still waiting
    to be let into the system.
    """
    docs = users_col.find({"role": {"$in": ["lmo", "gatc"]}, "status": "pending"})
    return [_to_user_out(d) for d in docs]


@router.get("", response_model=list[UserOut])
def list_all_officers(current_user: dict = Depends(role_required("admin"))):
    """All lmo/gatc accounts regardless of status, for the minister's oversight view."""
    docs = users_col.find({"role": {"$in": ["lmo", "gatc"]}})
    return [_to_user_out(d) for d in docs]


@router.post("/{user_id}/approve", response_model=UserOut)
def approve_user(user_id: str, current_user: dict = Depends(role_required("admin"))):
    user = _get_pending_or_processed_user(user_id)
    users_col.update_one({"_id": user["_id"]}, {"$set": {"status": "active"}})
    user["status"] = "active"
    return _to_user_out(user)


@router.post("/{user_id}/reject", response_model=UserOut)
def reject_user(user_id: str, current_user: dict = Depends(role_required("admin"))):
    user = _get_pending_or_processed_user(user_id)
    users_col.update_one({"_id": user["_id"]}, {"$set": {"status": "rejected"}})
    user["status"] = "rejected"
    return _to_user_out(user)
