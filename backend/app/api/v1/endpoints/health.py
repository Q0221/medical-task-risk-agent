"""健康检查接口。"""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy import text

from app.core.db import engine
from app.core.logger import get_logger
from app.core.redis import get_redis
from app.core.response import fail, success

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


@router.get("/healthz", summary="存活检查")
async def healthz() -> dict:
    return success({"status": "ok"})


@router.get("/readyz", summary="就绪检查（依赖 MySQL / Redis）")
async def readyz() -> JSONResponse:
    checks = {"mysql": False, "redis": False}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["mysql"] = True
    except Exception as exc:
        logger.warning("readyz mysql check failed: %s", exc)

    try:
        redis = get_redis()
        await redis.ping()
        checks["redis"] = True
    except (RedisError, RuntimeError) as exc:
        logger.warning("readyz redis check failed: %s", exc)

    if all(checks.values()):
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=success(checks),
        )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=fail(code=5031, message="dependencies not ready", data=checks),
    )
