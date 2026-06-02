"""FastAPI 应用入口。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logger import get_logger, setup_logging
from app.core.redis import close_redis, init_redis
from app.core.response import TraceIdMiddleware, register_exception_handlers

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s (env=%s) ...", settings.APP_NAME, settings.APP_ENV)
    await init_redis()
    try:
        yield
    finally:
        await close_redis()
        logger.info("Shutdown complete.")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        lifespan=lifespan,
    )

    app.add_middleware(TraceIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(api_router, prefix=settings.API_PREFIX)
    return app


app = create_app()
