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


def role_required(*allowed_roles: str):
    """FastAPI dependency factory for RBAC.
    Use like: def route(current_user: dict = Depends(role_required("owner")))
    """

    def checker(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized for this action",
            )
        return current_user

    return checker
