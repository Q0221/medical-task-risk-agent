"""Authentication endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_current_user
from app.core.response import success
from app.core.security import create_access_token
from app.schemas.auth import AuthUserOut, LoginRequest, LoginResponse
from app.services.auth_service import CurrentUser, authenticate_demo_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", summary="登录并签发访问令牌")
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(db_session),
) -> dict:
    user = await authenticate_demo_user(
        session,
        username=body.username,
        password=body.password,
        role=body.role,
    )
    token, expires_at_ts = create_access_token(
        user_id=user.id,
        role=user.role,
        role_codes=sorted(user.role_codes),
    )
    resp = LoginResponse(
        access_token=token,
        expires_at=datetime.fromtimestamp(expires_at_ts, tz=timezone.utc),
        user=_to_user_out(user),
    )
    return success(resp.model_dump(mode="json"))


@router.get("/me", summary="获取当前登录用户")
async def me(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    return success(_to_user_out(current_user).model_dump(mode="json"))


def _to_user_out(user: CurrentUser) -> AuthUserOut:
    return AuthUserOut(
        id=user.id,
        employee_no=user.employee_no,
        name=user.name,
        email=user.email,
        department=user.department,
        role=user.role,
        role_label=user.role_label,
        role_codes=sorted(user.role_codes),
        is_active=user.is_active,
    )
