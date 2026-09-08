import jwt
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config.db import users_col
from app.utils.security import decode_token

bearer_scheme = HTTPBearer()


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    """FastAPI dependency: verifies the JWT and returns the user document.
    Use like: def route(current_user: dict = Depends(get_current_user))
    """
    token = credentials.credentials
    try:
        user_id = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    try:
        user = users_col.find_one({"_id": ObjectId(user_id)})
    except InvalidId:
        raise HTTPException(status_code=401, detail="Invalid token subject")

    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")

    user["id"] = str(user["_id"])
    return user


def role_required(*allowed_roles: str, allow_admin_view: bool = False):
    """FastAPI dependency factory for RBAC.
    Use like: def route(current_user: dict = Depends(role_required("owner")))

    allow_admin_view=False (default): exact role match only, admin included
    unless explicitly listed. Nothing changes for existing routes.

    allow_admin_view=True: opt a route in to also letting an "admin" user
    through, in ADDITION to allowed_roles, even if "admin" isn't listed.
    Reserve this for read-only "look at this role's world" endpoints
    (e.g. dashboards) — never for owner/officer write actions like
    submitting applications or claiming inspections, where letting admin
    through would blur who actually performed the action.
    """

    def checker(current_user: dict = Depends(get_current_user)) -> dict:
        role = current_user["role"]
        is_allowed = role in allowed_roles or (allow_admin_view and role == "admin")
        if not is_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized for this action",
            )
        return current_user

    return checker