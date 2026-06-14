"""Notification Pydantic 模式（Phase 8 + 通知中心完善）。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

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
    is_read: bool = False
    # 关联任务的快照字段（查询时附加）
    task_status: Optional[str] = None
    task_created_at: Optional[datetime] = None
    task_remind_at: Optional[datetime] = None
    task_due_at: Optional[datetime] = None
    task_title: Optional[str] = None
    task_risk_level: Optional[str] = None
    task_type: Optional[str] = None


class NotificationListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    unread_count: int = 0
    items: List[NotificationOut]


class BatchReadRequest(BaseModel):
    """批量已读请求：提供 ids 则标记指定通知，不提供则标记当前用户所有未读。"""
    ids: Optional[List[int]] = None
