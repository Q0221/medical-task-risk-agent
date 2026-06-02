"""任务主表。

字段覆盖：
- 业务属性：类型、标题、描述、优先级、状态、来源
- 责任人：assignee（必填）、collaborators（JSON 多人）
- 关联：医院、产品、业务对象（type + id 两段式）
- 时间：提醒时间、截止时间、完成时间
- 风险：等级、原因、建议动作
- 审核：状态、审核人、审核备注、审核时间
- 元信息：trace_id、agent_session_id（短期记忆挂钩）
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel
from app.models.enums import (
    BusinessObjectType,
    ReviewStatus,
    RiskLevel,
    TaskPriority,
    TaskStatus,
    TaskType,
)


class Task(BaseModel):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_assignee_status", "assignee_id", "status"),
        Index("ix_tasks_remind_at_status", "remind_at", "status"),
        Index("ix_tasks_due_at_status", "due_at", "status"),
        Index("ix_tasks_business_object", "business_object_type", "business_object_id"),
    )

    type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=TaskType.OTHER.value,
        index=True,
        comment="任务类型",
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="agent", comment="来源：agent / form / webhook"
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=TaskStatus.PENDING.value,
        index=True,
    )
    priority: Mapped[str] = mapped_column(
        String(16), nullable=False, default=TaskPriority.MEDIUM.value, index=True
    )

    assignee_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="责任人",
    )
    collaborators: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="协作人 user_id 数组"
    )
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        comment="创建人 user_id",
    )

    hospital_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("hospitals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    product_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    business_object_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=BusinessObjectType.NONE.value,
        comment="业务对象类型",
    )
    business_object_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="业务对象 ID（不强外键，松耦合）"
    )

    remind_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, index=True, comment="提醒时间（Redis ZSet score 用）"
    )
    due_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, index=True, comment="截止时间"
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    risk_level: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=RiskLevel.LOW.value,
        index=True,
        comment="Risk Agent 输出的风险等级",
    )
    risk_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risk_suggested_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    review_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ReviewStatus.NONE.value,
        index=True,
        comment="人工审核状态",
    )
    reviewer_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    review_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    trace_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True, comment="创建该任务的 LangGraph trace_id"
    )
    agent_session_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="关联的会话 ID（短期记忆）"
    )
    extra: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="预留扩展字段（标签、SOP 链接、附件等）"
    )
