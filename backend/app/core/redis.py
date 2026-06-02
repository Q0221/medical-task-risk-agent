"""异步 Redis 客户端：在应用 lifespan 中初始化与关闭。"""

from typing import Optional

from redis.asyncio import Redis, from_url

from app.core.config import settings

_redis: Optional[Redis] = None


async def init_redis() -> Redis:
    """在应用启动时调用，创建全局 Redis 连接。"""
    global _redis
    if _redis is None:
        _redis = from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            health_check_interval=30,
        )
    return _redis


async def close_redis() -> None:
    """在应用关闭时调用，释放 Redis 连接。"""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


def get_redis() -> Redis:
    """FastAPI 依赖：返回已初始化的 Redis 客户端。"""
    if _redis is None:
        raise RuntimeError("Redis client is not initialized")
    return _redis
