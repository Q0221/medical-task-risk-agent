"""任务流转事件流。

每次任务的创建、分派、修改、评论、审核、提醒、完成等动作都落一条记录，
用于审计追踪与时间线展示。
"""

from typing import Optional

from sqlalchemy import JSON, BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class TaskEvent(BaseModel):
    __tablename__ = "task_events"

    task_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    operator_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="操作人；系统/Agent 触发时为 NULL",
    )
    operator_kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="user",
        comment="操作主体：user / agent / system",
    )
    payload: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="事件详情（旧值/新值/审核意见等）"
    )
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
