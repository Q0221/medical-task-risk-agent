"""FastAPI 应用入口。"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logger import get_logger, setup_logging
from app.core.redis import close_redis, init_redis
from app.core.response import TraceIdMiddleware, register_exception_handlers
from app.workers.notify_worker import NotifyWorker
from app.workers.reminder_worker import ReminderWorker

setup_logging()
logger = get_logger(__name__)

_reminder_worker: ReminderWorker | None = None
_notify_worker: NotifyWorker | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _reminder_worker, _notify_worker
    logger.info("Starting %s (env=%s) ...", settings.APP_NAME, settings.APP_ENV)
    await init_redis()

    # 启动 Reminder Worker（Phase 7）
    _reminder_worker = ReminderWorker()
    reminder_task = asyncio.create_task(_reminder_worker.run(), name="reminder_worker")

    # 启动 Notify Worker（Phase 8）
    _notify_worker = NotifyWorker()
    notify_task = asyncio.create_task(_notify_worker.run(), name="notify_worker")

    logger.info("Background workers started: reminder + notify")

    try:
        yield
    finally:
        for worker, task in [
            (_reminder_worker, reminder_task),
            (_notify_worker, notify_task),
        ]:
            if worker:
                worker.stop()
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=3)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
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
