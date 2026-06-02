"""API 通用依赖：DB Session、Redis、当前用户（占位）。"""

from typing import AsyncIterator

from fastapi import Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db as _get_db
from app.core.redis import get_redis as _get_redis


async def db_session() -> AsyncIterator[AsyncSession]:
    async for session in _get_db():
        yield session


def redis_client() -> Redis:
    return _get_redis()


def get_trace_id(request: Request) -> str:
    """取出由 TraceIdMiddleware 注入的 trace_id。"""
    return getattr(request.state, "trace_id", "")
