"""Reminder Worker（Phase 7）。

周期性扫描 Redis ZSet，处理到期提醒和逾期任务：
  - 每 SCAN_INTERVAL 秒执行一次
  - pop_due_reminders  → 写 Notification(task_reminder) + TaskEvent(reminder_sent)
  - pop_overdue_tasks  → 任务 status→overdue + Notification(task_overdue) + TaskEvent(update)

使用方式（在 main.py lifespan 中）：
    worker = ReminderWorker()
    asyncio.create_task(worker.run())
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import AsyncSessionLocal
from app.core.logger import get_logger
from app.core.redis import get_redis
from app.models.enums import NotificationChannel, NotificationKind, NotificationStatus, TaskEventType, TaskStatus
from app.models.notification import Notification
from app.models.task import Task
from app.models.task_event import TaskEvent
from app.services.reminder_service import pop_due_reminders, pop_overdue_tasks

logger = get_logger(__name__)

SCAN_INTERVAL = 30          # 秒：两次扫描间隔
MAX_BATCH = 50              # 单次最多处理条数


class ReminderWorker:
    """后台提醒工作者，在应用 lifespan 中作为 asyncio Task 运行。"""

    def __init__(self, scan_interval: int = SCAN_INTERVAL) -> None:
        self._interval = scan_interval
        self._running = False

    async def run(self) -> None:
        """入口：无限循环，每隔 _interval 秒扫描一次。"""
        self._running = True
        logger.info("ReminderWorker started (interval=%ds)", self._interval)
        while self._running:
            try:
                await self._tick()
            except Exception as exc:
                logger.exception("ReminderWorker tick error: %s", exc)
            await asyncio.sleep(self._interval)

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # 核心扫描
    # ------------------------------------------------------------------

    async def _tick(self) -> None:
        redis = get_redis()
        now = datetime.now(timezone.utc)

        # 1. 处理到期提醒
        reminder_ids = await pop_due_reminders(redis, now=now, limit=MAX_BATCH)
        if reminder_ids:
            await self._handle_reminders(reminder_ids)

        # 2. 处理逾期截止
        overdue_ids = await pop_overdue_tasks(redis, now=now, limit=MAX_BATCH)
        if overdue_ids:
            await self._handle_overdue(overdue_ids)

    # ------------------------------------------------------------------
    # 到期提醒处理
    # ------------------------------------------------------------------

    async def _handle_reminders(self, task_ids: list[int]) -> None:
        """对每个到期任务写 Notification + TaskEvent。"""
        async with AsyncSessionLocal() as session:
            async with session.begin():
                for task_id in task_ids:
                    task = await _get_task(session, task_id)
                    if task is None:
                        logger.warning("reminder: task_id=%s not found, skip", task_id)
                        continue
                    if task.status in (TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value):
                        logger.info("reminder: task_id=%s already %s, skip", task_id, task.status)
                        continue

                    title = f"任务提醒：{task.title}"
                    content = _build_reminder_content(task)

                    notif = Notification(
                        task_id=task_id,
                        kind=NotificationKind.TASK_REMINDER.value,
                        channel=NotificationChannel.IM.value,
                        recipient_user_id=task.assignee_id,
                        title=title,
                        content=content,
                        status=NotificationStatus.PENDING.value,
                        payload={"remind_at": task.remind_at.isoformat() if task.remind_at else None},
                    )
                    session.add(notif)

                    session.add(TaskEvent(
                        task_id=task_id,
                        event_type=TaskEventType.REMINDER_SENT.value,
                        operator_id=None,
                        operator_kind="system",
                        payload={"remind_at": task.remind_at.isoformat() if task.remind_at else None,
                                 "title": title},
                    ))
                    logger.info("reminder processed: task_id=%s assignee=%s", task_id, task.assignee_id)

    # ------------------------------------------------------------------
    # 逾期截止处理
    # ------------------------------------------------------------------

    async def _handle_overdue(self, task_ids: list[int]) -> None:
        """将逾期任务状态更新为 overdue，写 Notification + TaskEvent。"""
        _skip_statuses = {
            TaskStatus.COMPLETED.value,
            TaskStatus.CANCELLED.value,
            TaskStatus.AWAITING_REVIEW.value,
            TaskStatus.OVERDUE.value,
        }
        async with AsyncSessionLocal() as session:
            async with session.begin():
                for task_id in task_ids:
                    task = await _get_task(session, task_id)
                    if task is None:
                        logger.warning("overdue: task_id=%s not found, skip", task_id)
                        continue
                    if task.status in _skip_statuses:
                        logger.info("overdue: task_id=%s status=%s, skip", task_id, task.status)
                        continue

                    old_status = task.status
                    task.status = TaskStatus.OVERDUE.value

                    title = f"任务逾期：{task.title}"
                    content = _build_overdue_content(task)

                    notif = Notification(
                        task_id=task_id,
                        kind=NotificationKind.TASK_OVERDUE.value,
                        channel=NotificationChannel.IM.value,
                        recipient_user_id=task.assignee_id,
                        title=title,
                        content=content,
                        status=NotificationStatus.PENDING.value,
                        payload={
                            "due_at": task.due_at.isoformat() if task.due_at else None,
                            "old_status": old_status,
                        },
                    )
                    session.add(notif)

                    session.add(TaskEvent(
                        task_id=task_id,
                        event_type=TaskEventType.UPDATE.value,
                        operator_id=None,
                        operator_kind="system",
                        payload={
                            "reason": "overdue",
                            "old_status": old_status,
                            "new_status": TaskStatus.OVERDUE.value,
                            "due_at": task.due_at.isoformat() if task.due_at else None,
                        },
                    ))
                    logger.info(
                        "task overdue: task_id=%s old_status=%s assignee=%s",
                        task_id, old_status, task.assignee_id,
                    )


# ------------------------------------------------------------------
# 工具函数
# ------------------------------------------------------------------

async def _get_task(session: AsyncSession, task_id: int) -> Optional[Task]:
    return (
        await session.execute(
            select(Task).where(Task.id == task_id, Task.deleted_at.is_(None))
        )
    ).scalar_one_or_none()


def _build_reminder_content(task: Task) -> str:
    lines = [f"您有一个任务即将到期，请及时处理。"]
    lines.append(f"任务标题：{task.title}")
    lines.append(f"任务类型：{task.type}")
    lines.append(f"当前优先级：{task.priority}")
    if task.remind_at:
        lines.append(f"提醒时间：{task.remind_at.strftime('%Y-%m-%d %H:%M')}")
    if task.due_at:
        lines.append(f"截止时间：{task.due_at.strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


def _build_overdue_content(task: Task) -> str:
    lines = ["您有一个任务已逾期，请尽快处理或更新截止时间。"]
    lines.append(f"任务标题：{task.title}")
    lines.append(f"任务类型：{task.type}")
    if task.due_at:
        lines.append(f"原截止时间：{task.due_at.strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


__all__ = ["ReminderWorker"]
