from fastapi import APIRouter, Depends, HTTPException, Request
from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from app.config.db import users_col, states_col, districts_col, refresh_tokens_col, otp_verifications_col
from app.middleware.auth import role_required
from app.models.user import UserOut, OfficerCreate, OfficerCreatedOut
from app.utils.security import hash_password, generate_temp_password
from app.services.audit import log_event
from app.services.mailer import (
    send_officer_credentials,
    send_admin_password_reset,
    is_configured as smtp_is_configured,
)
from app.services.jobs import get_queue, send_officer_credentials_job, send_admin_password_reset_job

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
        mfa_enabled=bool(doc.get("mfa_enabled", False)),
    )


@router.post("/create-officer", response_model=OfficerCreatedOut, status_code=201)
def create_officer(payload: OfficerCreate, request: Request, current_user: dict = Depends(role_required("admin"))):
    """The only way an lmo/gatc account comes into existence. There is no
    public registration path for these roles — the admin picks who gets
    to be an officer, full stop. The account is active immediately
    (the admin creating it is the approval); a one-time temp password is
    generated and returned here, and the officer is forced to change it
    the first time they log in."""
    actor = str(current_user["_id"])
    target_email = payload.email.lower()

    def _refuse(detail: str, message: str, status_code: int = 400):
        log_event(
            "officer_creation_failed", outcome="failure", request=request,
            email=target_email, actor_id=actor, actor_email=current_user["email"], detail=detail,
        )
        raise HTTPException(status_code=status_code, detail=message)

    if payload.role not in ("lmo", "gatc"):
        _refuse("invalid_role", "role must be 'lmo' or 'gatc'")

    if not states_col.find_one({"code": payload.jurisdiction.state_code}):
        _refuse("unknown_state", f"Unknown state_code '{payload.jurisdiction.state_code}'")
    if payload.jurisdiction.district_code and not districts_col.find_one(
        {"code": payload.jurisdiction.district_code, "state_code": payload.jurisdiction.state_code}
    ):
        _refuse("unknown_district", f"Unknown district_code '{payload.jurisdiction.district_code}'")

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
        _refuse("email_exists", "Email already registered", 409)

    doc["_id"] = result.inserted_id

    log_event(
        "officer_created",
        outcome="success",
        request=request,
        email=doc["email"],
        user_id=str(result.inserted_id),
        role=doc["role"],
        actor_id=actor,
        actor_email=current_user["email"],
        detail=f"jurisdiction={payload.jurisdiction.state_code}/{payload.jurisdiction.district_code or '*'}",
    )

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
def approve_user(user_id: str, request: Request, current_user: dict = Depends(role_required("admin"))):
    """Also doubles as "reactivate": since officer accounts are now
    created active by /create-officer, this mostly matters for
    un-suspending an officer previously rejected below."""
    user = _get_pending_or_processed_user(user_id)
    previous = user.get("status", "active")
    users_col.update_one({"_id": user["_id"]}, {"$set": {"status": "active"}})
    user["status"] = "active"
    log_event(
        "account_approved",
        outcome="success",
        request=request,
        email=user["email"],
        user_id=str(user["_id"]),
        role=user["role"],
        actor_id=str(current_user["_id"]),
        actor_email=current_user["email"],
        detail=f"from={previous}",
    )
    return _to_user_out(user)


@router.post("/{user_id}/reject", response_model=UserOut)
def reject_user(user_id: str, request: Request, current_user: dict = Depends(role_required("admin"))):
    """Also doubles as "suspend": blocks an existing officer's account from
    logging in, e.g. if they're no longer authorized.

    Suspending also ends the officer's sessions right now (token_version bump
    kills every access token; every refresh token is revoked). Without this a
    suspended officer would stay signed in for as long as their browser kept
    renewing its session."""
    user = _get_pending_or_processed_user(user_id)
    previous = user.get("status", "active")
    users_col.update_one(
        {"_id": user["_id"]},
        {"$set": {"status": "rejected"}, "$inc": {"token_version": 1}},
    )
    refresh_tokens_col.update_many({"user_id": str(user["_id"]), "revoked": False}, {"$set": {"revoked": True}})
    user["status"] = "rejected"
    log_event(
        "account_suspended",
        outcome="success",
        request=request,
        email=user["email"],
        user_id=str(user["_id"]),
        role=user["role"],
        actor_id=str(current_user["_id"]),
        actor_email=current_user["email"],
        detail=f"from={previous}",
    )
    return _to_user_out(user)


@router.post("/{user_id}/reset-mfa", response_model=UserOut)
def admin_reset_officer_mfa(
    user_id: str,
    request: Request,
    current_user: dict = Depends(role_required("admin")),
):
    """Clears an officer's two-step verification so they can enrol a new
    authenticator at their next sign-in — for a lost or replaced phone, or
    when they've used up their recovery codes. They are signed out everywhere.

    Officers only (lmo/gatc). The admin account's own two-step verification is
    reset by the operator with `reset_mfa.py` — no API can do it, so a
    compromised admin session can never strip another admin's second factor."""
    user = _get_pending_or_processed_user(user_id)

    users_col.update_one(
        {"_id": user["_id"]},
        {
            "$set": {"mfa_enabled": False},
            "$unset": {
                "mfa_secret_enc": "",
                "mfa_pending_secret": "",
                "mfa_pending_at": "",
                "mfa_last_step": "",
                "mfa_recovery_hashes": "",
                "mfa_enabled_at": "",
            },
            "$inc": {"token_version": 1},
        },
    )
    refresh_tokens_col.update_many({"user_id": str(user["_id"]), "revoked": False}, {"$set": {"revoked": True}})

    log_event(
        "mfa_reset",
        outcome="success",
        request=request,
        email=user["email"],
        user_id=str(user["_id"]),
        role=user["role"],
        actor_id=str(current_user["_id"]),
        actor_email=current_user["email"],
    )
    user["mfa_enabled"] = False
    return _to_user_out(user)


@router.post("/{user_id}/reset-password", response_model=OfficerCreatedOut)
def admin_reset_officer_password(
    user_id: str,
    request: Request,
    current_user: dict = Depends(role_required("admin")),
):
    """The ONLY way an lmo/gatc officer's forgotten password gets reset —
    officers cannot use the self-service "forgot password" flow (see
    SELF_SERVICE_AUTH_ROLES in config/settings.py), so a hijacked mailbox
    is never enough to take over an officer account.

    Generates a one-time temporary password (shown to the admin once in
    this response, and emailed to the officer), forces a password change on
    next login, signs the officer out everywhere, clears any lockout, and
    cancels any pending reset code. Admin accounts cannot be reset here —
    the super admin is recovered by the operator with `seed_super_admin.py`."""
    # Reuses the same lookup/guard as approve/reject: valid ObjectId, user
    # exists, and role is lmo/gatc (never owner or admin).
    user = _get_pending_or_processed_user(user_id)

    temp_password = generate_temp_password()
    users_col.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "password": hash_password(temp_password),
                "must_change_password": True,
                "failed_login_attempts": 0,
            },
            "$unset": {"locked_until": ""},
            "$inc": {"token_version": 1},
        },
    )
    refresh_tokens_col.update_many({"user_id": str(user["_id"]), "revoked": False}, {"$set": {"revoked": True}})
    otp_verifications_col.delete_many({"identifier": user["email"], "purpose": "password_reset"})

    log_event(
        "admin_password_reset",
        outcome="success",
        request=request,
        email=user["email"],
        user_id=str(user["_id"]),
        role=user["role"],
        actor_id=str(current_user["_id"]),
        actor_email=current_user["email"],
    )

    emailed = False
    if smtp_is_configured():
        queue = get_queue()
        if queue is not None:
            try:
                queue.enqueue(
                    send_admin_password_reset_job,
                    to=user["email"], name=user["name"], temp_password=temp_password,
                )
                emailed = True
            except Exception:
                emailed = False
        else:
            emailed = send_admin_password_reset(to=user["email"], name=user["name"], temp_password=temp_password)

    user["must_change_password"] = True
    return OfficerCreatedOut(user=_to_user_out(user), temp_password=temp_password, emailed=emailed)
