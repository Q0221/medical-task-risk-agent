"""Notification Pydantic 模式（Phase 8）。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    """通知记录响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: Optional[int]
    kind: str
    channel: str
    recipient_user_id: Optional[int]
    recipient_address: Optional[str]
    title: Optional[str]
    content: Optional[str]
    status: str
    retry_count: int
    sent_at: Optional[datetime]
    error_message: Optional[str]
    created_at: datetime
    task_status: Optional[str] = None
    task_created_at: Optional[datetime] = None
    task_remind_at: Optional[datetime] = None
    task_due_at: Optional[datetime] = None


class NotificationListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[NotificationOut]
