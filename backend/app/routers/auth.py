from fastapi import APIRouter, Depends, HTTPException
from pymongo.errors import DuplicateKeyError

from app.config.db import users_col
from app.config.constants import ROLES
from app.models.user import UserRegister, UserLogin, UserOut, TokenResponse
from app.utils.security import hash_password, verify_password, create_token
from app.middleware.auth import get_current_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def to_user_out(user_doc: dict) -> UserOut:
    return UserOut(
        id=str(user_doc["_id"]),
        name=user_doc["name"],
        email=user_doc["email"],
        role=user_doc["role"],
        # Older documents created before the approval-gate feature won't
        # have a status field at all — treat those as active so existing
        # accounts don't get silently locked out by this change.
        status=user_doc.get("status", "active"),
        org_type=user_doc.get("org_type"),
        org_name=user_doc.get("org_name"),
        contact=user_doc.get("contact"),
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: UserRegister):
    if payload.role not in ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {ROLES}")

    if payload.role == "admin":
        # The minister / department-head account is provisioned exclusively
        # by seed_super_admin.py, never through open self-registration.
        raise HTTPException(status_code=403, detail="This role cannot self-register")

    # Owners can use their account right away. lmo/gatc accounts represent
    # real government officers, so they sit in "pending" until the admin
    # (minister) approves them — see /admin/users/{id}/approve below.
    status = "active" if payload.role == "owner" else "pending"

    doc = {
        "name": payload.name,
        "email": payload.email.lower(),
        "password": hash_password(payload.password),
        "role": payload.role,
        "status": status,
        "org_type": payload.org_type,
        "org_name": payload.org_name,
        "contact": payload.contact,
    }

    try:
        result = users_col.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Email already registered")

    doc["_id"] = result.inserted_id

    if status == "pending":
        # No token for a pending account — they can't do anything yet.
        # The frontend should show "awaiting admin approval" rather than
        # logging them straight in.
        return TokenResponse(user=to_user_out(doc), token="")

    token = create_token(str(result.inserted_id))
    return TokenResponse(user=to_user_out(doc), token=token)


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin):
    user = users_col.find_one({"email": payload.email.lower()})
    if not user or not verify_password(payload.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user_status = user.get("status", "active")  # see to_user_out() for why the fallback
    if user_status == "pending":
        raise HTTPException(status_code=403, detail="Your account is awaiting admin approval")
    if user_status == "rejected":
        raise HTTPException(status_code=403, detail="Your account registration was not approved")

    token = create_token(str(user["_id"]))
    return TokenResponse(user=to_user_out(user), token=token)


@router.get("/me", response_model=UserOut)
def me(current_user: dict = Depends(get_current_user)):
    return to_user_out(current_user)