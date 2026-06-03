"""Agent 会话状态服务（Phase 6+）。

用 Redis 存储多轮对话中的 pending 任务草稿，支持：
- 保存待补全草稿（clarify 阶段）
- 读取并清除（一次性取出，完成后删除）
- TTL 默认 30 分钟（超时则用户需重新描述）

Redis key 格式：`agent_session:{session_id}`
"""

from __future__ import annotations

import json
import uuid
from typing import Optional

from redis.asyncio import Redis

from app.core.logger import get_logger

logger = get_logger(__name__)

_SESSION_TTL = 1800  # 30 分钟


class PendingDraft:
    """Redis 中存储的待补全草稿结构。"""

    __slots__ = ("draft_raw", "pending_field", "pending_question", "user_id")

    def __init__(
        self,
        draft_raw: dict,
        pending_field: str,
        pending_question: str,
        user_id: Optional[int] = None,
    ):
        self.draft_raw = draft_raw
        self.pending_field = pending_field
        self.pending_question = pending_question
        self.user_id = user_id

    def to_dict(self) -> dict:
        return {
            "draft_raw": self.draft_raw,
            "pending_field": self.pending_field,
            "pending_question": self.pending_question,
            "user_id": self.user_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PendingDraft":
        return cls(
            draft_raw=data["draft_raw"],
            pending_field=data["pending_field"],
            pending_question=data["pending_question"],
            user_id=data.get("user_id"),
        )


def generate_session_id() -> str:
    return uuid.uuid4().hex


async def save_pending(
    redis: Redis,
    session_id: str,
    pending: PendingDraft,
) -> None:
    key = f"agent_session:{session_id}"
    await redis.set(key, json.dumps(pending.to_dict(), ensure_ascii=False), ex=_SESSION_TTL)
    logger.info("session saved: session_id=%s pending_field=%s", session_id, pending.pending_field)


async def load_pending(
    redis: Redis,
    session_id: str,
) -> Optional[PendingDraft]:
    """读取 pending 草稿（不删除，等 consume_pending 清除）。"""
    if not session_id:
        return None
    key = f"agent_session:{session_id}"
    raw = await redis.get(key)
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        return PendingDraft.from_dict(data)
    except Exception:
        logger.warning("failed to parse session data for session_id=%s", session_id)
        return None


async def consume_pending(
    redis: Redis,
    session_id: str,
) -> Optional[PendingDraft]:
    """读取并删除 pending 草稿（任务创建成功后调用）。"""
    pending = await load_pending(redis, session_id)
    if pending is not None:
        await redis.delete(f"agent_session:{session_id}")
        logger.info("session consumed: session_id=%s", session_id)
    return pending


async def clear_session(redis: Redis, session_id: str) -> None:
    if session_id:
        await redis.delete(f"agent_session:{session_id}")


__all__ = [
    "PendingDraft",
    "generate_session_id",
    "save_pending",
    "load_pending",
    "consume_pending",
    "clear_session",
]
