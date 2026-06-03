"""Reminder 服务：基于 Redis ZSet 的延迟提醒与截止日期追踪（Phase 7）。

Redis 数据结构：
  task:reminders  ZSet  —  score = remind_at Unix 时间戳（秒）
  task:deadlines  ZSet  —  score = due_at   Unix 时间戳（秒）

对外接口（供 endpoint / worker 调用）：
  schedule_reminder(redis, task_id, remind_at)   注册提醒
  cancel_reminder(redis, task_id)               取消提醒
  pop_due_reminders(redis, now, limit)          原子取出到期提醒
  schedule_deadline(redis, task_id, due_at)     注册截止日期追踪
  cancel_deadline(redis, task_id)              取消截止日期追踪
  pop_overdue_tasks(redis, now, limit)         原子取出逾期任务
  get_scheduled_reminders(redis)               查询所有已排期（调试用）
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from redis.asyncio import Redis

from app.core.logger import get_logger

logger = get_logger(__name__)

REMINDER_ZSET = "task:reminders"
DEADLINE_ZSET = "task:deadlines"


# ---------------------------------------------------------------------------
# 提醒时间（remind_at）
# ---------------------------------------------------------------------------

async def schedule_reminder(
    redis: Redis,
    task_id: int,
    remind_at: datetime,
) -> None:
    """将任务加入提醒 ZSet，score = remind_at 的 Unix 时间戳。"""
    score = _to_ts(remind_at)
    await redis.zadd(REMINDER_ZSET, {str(task_id): score})
    logger.info("reminder scheduled: task_id=%s remind_at=%s", task_id, remind_at.isoformat())


async def cancel_reminder(redis: Redis, task_id: int) -> None:
    """从提醒 ZSet 移除任务。"""
    removed = await redis.zrem(REMINDER_ZSET, str(task_id))
    if removed:
        logger.info("reminder cancelled: task_id=%s", task_id)


async def pop_due_reminders(
    redis: Redis,
    now: Optional[datetime] = None,
    limit: int = 50,
) -> list[int]:
    """原子地取出并删除所有 score <= now 的到期提醒，返回 task_id 列表。"""
    ts = _to_ts(now or datetime.now(timezone.utc))
    items = await redis.zrangebyscore(REMINDER_ZSET, "-inf", ts, start=0, num=limit)
    if not items:
        return []
    await redis.zrem(REMINDER_ZSET, *items)
    task_ids = [int(i) for i in items]
    logger.info("popped %d due reminders: %s", len(task_ids), task_ids)
    return task_ids


async def get_scheduled_reminders(redis: Redis) -> list[tuple[int, datetime]]:
    """查询所有已排期的提醒（调试 / 管理接口用）。"""
    raw = await redis.zrangebyscore(REMINDER_ZSET, "-inf", "+inf", withscores=True)
    return [(int(member), _from_ts(score)) for member, score in raw]


# ---------------------------------------------------------------------------
# 截止时间（due_at）
# ---------------------------------------------------------------------------

async def schedule_deadline(
    redis: Redis,
    task_id: int,
    due_at: datetime,
) -> None:
    """将任务截止时间加入 ZSet，供逾期检测。"""
    score = _to_ts(due_at)
    await redis.zadd(DEADLINE_ZSET, {str(task_id): score})
    logger.info("deadline scheduled: task_id=%s due_at=%s", task_id, due_at.isoformat())


async def cancel_deadline(redis: Redis, task_id: int) -> None:
    await redis.zrem(DEADLINE_ZSET, str(task_id))


async def pop_overdue_tasks(
    redis: Redis,
    now: Optional[datetime] = None,
    limit: int = 50,
) -> list[int]:
    """原子地取出并删除所有已逾期（due_at <= now）的任务 ID 列表。"""
    ts = _to_ts(now or datetime.now(timezone.utc))
    items = await redis.zrangebyscore(DEADLINE_ZSET, "-inf", ts, start=0, num=limit)
    if not items:
        return []
    await redis.zrem(DEADLINE_ZSET, *items)
    task_ids = [int(i) for i in items]
    logger.info("popped %d overdue tasks: %s", len(task_ids), task_ids)
    return task_ids


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def _to_ts(dt: datetime) -> float:
    """datetime → Unix 时间戳（秒，float）。naive datetime 视为 UTC。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).timestamp()
    return dt.timestamp()


def _from_ts(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)


__all__ = [
    "REMINDER_ZSET",
    "DEADLINE_ZSET",
    "schedule_reminder",
    "cancel_reminder",
    "pop_due_reminders",
    "get_scheduled_reminders",
    "schedule_deadline",
    "cancel_deadline",
    "pop_overdue_tasks",
]
