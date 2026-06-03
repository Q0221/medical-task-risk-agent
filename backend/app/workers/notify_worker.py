"""Notify Worker（Phase 8）。

周期性扫描 notifications 表中 status=pending 或 status=failed（且 retry < MAX_RETRY）
的记录，逐条调用 notify_agent.dispatch_notification 分发。

使用方式（在 main.py lifespan 中）：
    worker = NotifyWorker()
    asyncio.create_task(worker.run(), name="notify_worker")
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.agents.notify_agent import MAX_RETRY, dispatch_notification
from app.core.db import AsyncSessionLocal
from app.core.logger import get_logger
from app.models.enums import NotificationStatus
from app.models.notification import Notification

logger = get_logger(__name__)

POLL_INTERVAL = 15   # 秒：两次轮询间隔
BATCH_SIZE = 20      # 单次最多处理条数

_DISPATCHABLE = [
    NotificationStatus.PENDING.value,
    NotificationStatus.FAILED.value,
]


class NotifyWorker:
    """后台通知工作者，在应用 lifespan 中作为 asyncio Task 运行。"""

    def __init__(self, poll_interval: int = POLL_INTERVAL) -> None:
        self._interval = poll_interval
        self._running = False

    async def run(self) -> None:
        self._running = True
        logger.info("NotifyWorker started (interval=%ds)", self._interval)
        while self._running:
            try:
                await self._tick()
            except Exception as exc:
                logger.exception("NotifyWorker tick error: %s", exc)
            await asyncio.sleep(self._interval)

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------

    async def _tick(self) -> None:
        # 第一步：查出待分发的通知 ID 列表（只取 ID，避免跨 session 使用 ORM 对象）
        async with AsyncSessionLocal() as session:
            async with session.begin():
                id_rows = (
                    await session.execute(
                        select(Notification.id)
                        .where(
                            Notification.status.in_(_DISPATCHABLE),
                            Notification.retry_count < MAX_RETRY,
                            Notification.deleted_at.is_(None),
                        )
                        .order_by(Notification.created_at)
                        .limit(BATCH_SIZE)
                    )
                ).scalars().all()

        if not id_rows:
            return

        logger.info("NotifyWorker: dispatching %d notifications", len(id_rows))

        # 第二步：每条通知独立 session + 事务，互不干扰
        for notif_id in id_rows:
            try:
                async with AsyncSessionLocal() as session:
                    async with session.begin():
                        notif = (
                            await session.execute(
                                select(Notification).where(Notification.id == notif_id)
                            )
                        ).scalar_one_or_none()
                        if notif is None:
                            continue
                        await dispatch_notification(session, notif)
            except Exception as exc:
                logger.exception(
                    "dispatch failed for notification_id=%s: %s",
                    notif_id, exc,
                )


__all__ = ["NotifyWorker"]
