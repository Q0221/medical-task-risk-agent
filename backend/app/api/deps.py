"""API common dependencies: DB session, Redis and current user."""

from typing import AsyncIterator

from fastapi import Depends, Header, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import AsyncSessionLocal, get_db as _get_db
from app.core.exceptions import BizException
from app.core.redis import get_redis as _get_redis
from app.core.security import TokenError, decode_access_token
from app.services.auth_service import CurrentUser, get_current_user_by_id


async def db_session() -> AsyncIterator[AsyncSession]:
    async for session in _get_db():
        yield session


def redis_client() -> Redis:
    return _get_redis()


def get_trace_id(request: Request) -> str:
    return getattr(request.state, "trace_id", "")


async def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> CurrentUser:
    """Resolve and validate the bearer token for protected APIs."""
    if not authorization:
        raise BizException(code=4010, message="请先登录")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise BizException(code=4010, message="登录凭证格式不正确，请重新登录")

    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (TokenError, ValueError, KeyError):
        raise BizException(code=4011, message="登录已过期，请重新登录")

    async with AsyncSessionLocal() as session:
        user = await get_current_user_by_id(session, user_id)

    if user is None:
        raise BizException(code=4011, message="登录用户不存在，请重新登录")
    if not user.is_active:
        raise BizException(code=4012, message="账号已停用，请联系管理员")
    return user


def require_app_roles(*allowed_roles: str):
    allowed = set(allowed_roles)

    async def _guard(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if current_user.role not in allowed:
            raise BizException(code=4030, message="当前账号没有权限执行该操作")
        return current_user

    return _guard
