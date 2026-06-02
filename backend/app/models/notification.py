"""通知发送记录。

支持企业微信 / 邮件 / 站内消息 / 短信多渠道；
支持任务通知、到期提醒、高风险审核、知识补充任务、日报周报等场景；
失败重试与死信状态。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel
from app.models.enums import NotificationChannel, NotificationKind, NotificationStatus


class Notification(BaseModel):
    __tablename__ = "notifications"

    task_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="关联任务（日报/周报可为空）",
    )
    kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=NotificationKind.TASK_CREATED.value,
        index=True,
        comment="通知业务场景",
    )
    channel: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=NotificationChannel.WXWORK.value,
        index=True,
    )
    recipient_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="收件人 user_id",
    )
    recipient_address: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="收件人地址快照（邮箱 / wxwork_userid），用于审计",
    )
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="渠道原始 payload / 模板变量"
    )

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=NotificationStatus.PENDING.value,
        index=True,
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
