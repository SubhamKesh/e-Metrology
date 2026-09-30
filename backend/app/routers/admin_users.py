from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from app.config.db import users_col, states_col, districts_col
from app.middleware.auth import role_required
from app.models.user import UserOut, OfficerCreate, OfficerCreatedOut
from app.utils.security import hash_password, generate_temp_password
from app.services.mailer import send_officer_credentials, is_configured as smtp_is_configured
from app.services.jobs import get_queue, send_officer_credentials_job

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
        jurisdiction=doc.get("jurisdiction"),
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

    if not states_col.find_one({"code": payload.jurisdiction.state_code}):
        raise HTTPException(status_code=400, detail=f"Unknown state_code '{payload.jurisdiction.state_code}'")
    if payload.jurisdiction.district_code and not districts_col.find_one(
        {"code": payload.jurisdiction.district_code, "state_code": payload.jurisdiction.state_code}
    ):
        raise HTTPException(status_code=400, detail=f"Unknown district_code '{payload.jurisdiction.district_code}'")

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
        "jurisdiction": payload.jurisdiction.dict(),
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

    # `emailed` used to mean "SMTP confirmed it accepted the message" --
    # found out synchronously, right here, by blocking this response on
    # the SMTP round-trip. Now the actual send happens in a background
    # worker (so a slow/unreachable mail server can't hold up officer
    # creation), so `emailed` means "we've queued it and it will be
    # attempted" instead. is_configured() is just an env-var check (no
    # network), so it's fine to keep that part synchronous -- it's what
    # lets an admin know immediately whether to expect the email at all,
    # versus needing to share the temp password with this officer some
    # other way right now.
    emailed = False
    if smtp_is_configured():
        queue = get_queue()
        if queue is not None:
            try:
                queue.enqueue(
                    send_officer_credentials_job,
                    to=doc["email"], name=doc["name"], role=doc["role"], temp_password=temp_password,
                )
                emailed = True
            except Exception:
                emailed = False
        else:
            # No Redis configured -- fall back to sending inline, exactly
            # as before this queue existed.
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
