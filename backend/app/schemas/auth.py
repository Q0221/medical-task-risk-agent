"""Authentication request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


AppRole = Literal["employee", "manager", "operator", "admin"]


class LoginRequest(BaseModel):
    username: Optional[str] = Field(default=None, max_length=128)
    password: str = Field(..., min_length=1, max_length=128)
    role: Optional[AppRole] = Field(default=None)


class AuthUserOut(BaseModel):
    id: int
    employee_no: str
    name: str
    email: Optional[str] = None
    department: Optional[str] = None
    role: AppRole
    role_label: str
    role_codes: list[str]
    is_active: bool


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: AuthUserOut
