from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from app.config.db import users_col
from app.middleware.auth import role_required
from app.models.user import UserOut, OfficerCreate, OfficerCreatedOut
from app.utils.security import hash_password, generate_temp_password
from app.services.mailer import send_officer_credentials

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
        must_change_password=doc.get("must_change_password", False),
    )


@router.post("/create-officer", response_model=OfficerCreatedOut, status_code=201)
def create_officer(payload: OfficerCreate, current_user: dict = Depends(role_required("admin"))):
    """The only way an lmo/gatc account comes into existence. There is no
    public registration path for these roles — the admin picks who gets
    to be an officer, full stop. The account is active immediately
    (the admin creating it is the approval); a one-time temp password is
    generated and returned here, and the officer is forced to change it
    the first time they log in."""
    if payload.role not in ("lmo", "gatc"):
        raise HTTPException(status_code=400, detail="role must be 'lmo' or 'gatc'")

    temp_password = generate_temp_password()

    doc = {
        "name": payload.name,
        "email": payload.email.lower(),
        "password": hash_password(temp_password),
        "role": payload.role,
        "status": "active",
        "org_type": payload.org_type or ("LMO" if payload.role == "lmo" else "GATC"),
        "org_name": payload.org_name,
        "contact": payload.contact,
        "token_version": 0,
        "failed_login_attempts": 0,
        "must_change_password": True,
        "created_by": str(current_user["_id"]),
    }

    try:
        result = users_col.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Email already registered")

    doc["_id"] = result.inserted_id

    emailed = send_officer_credentials(
        to=doc["email"], name=doc["name"], role=doc["role"], temp_password=temp_password
    )

    return OfficerCreatedOut(user=_to_user_out(doc), temp_password=temp_password, emailed=emailed)


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
    """Also doubles as "reactivate": since officer accounts are now
    created active by /create-officer, this mostly matters for
    un-suspending an officer previously rejected below."""
    user = _get_pending_or_processed_user(user_id)
    users_col.update_one({"_id": user["_id"]}, {"$set": {"status": "active"}})
    user["status"] = "active"
    return _to_user_out(user)


@router.post("/{user_id}/reject", response_model=UserOut)
def reject_user(user_id: str, current_user: dict = Depends(role_required("admin"))):
    """Also doubles as "suspend": blocks an existing officer's account from
    logging in, e.g. if they're no longer authorized."""
    user = _get_pending_or_processed_user(user_id)
    users_col.update_one({"_id": user["_id"]}, {"$set": {"status": "rejected"}})
    user["status"] = "rejected"
    return _to_user_out(user)
