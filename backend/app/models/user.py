from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=6)
    role: str  # must be one of ROLES — validated in the router
    org_type: Optional[str] = None  # "LMO" or "GATC", only relevant for those roles
    org_name: Optional[str] = None
    contact: Optional[str] = None
    # Deliberately NO status field here — a registering user can never set
    # their own approval status. The router decides it based on role.


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: str
    status: str
    org_type: Optional[str] = None
    org_name: Optional[str] = None
    contact: Optional[str] = None


class TokenResponse(BaseModel):
    user: UserOut
    token: str