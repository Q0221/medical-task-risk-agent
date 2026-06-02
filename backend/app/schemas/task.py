"""任务相关 Pydantic 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    BusinessObjectType,
    ReviewStatus,
    RiskLevel,
    TaskPriority,
    TaskStatus,
    TaskType,
)


class TaskDraft(BaseModel):
    """Agent 抽取出的任务草稿（在落库前的中间态）。"""

    model_config = ConfigDict(use_enum_values=True)

    title: str
    type: TaskType
    priority: TaskPriority = TaskPriority.MEDIUM
    description: Optional[str] = None

    assignee_name: Optional[str] = None
    hospital_name: Optional[str] = None
    product_name: Optional[str] = None

    business_object_type: BusinessObjectType = BusinessObjectType.NONE
    business_object_id: Optional[str] = None

    remind_at: Optional[datetime] = None
    due_at: Optional[datetime] = None

    risk_keywords: List[str] = Field(default_factory=list)


class TaskDetail(BaseModel):
    """任务对外响应模型。"""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: int
    type: str
    title: str
    description: Optional[str]
    source: str
    status: str
    priority: str

    assignee_id: int
    collaborators: Optional[list] = None
    created_by: int

    hospital_id: Optional[int]
    product_id: Optional[int]
    business_object_type: str
    business_object_id: Optional[str]

    remind_at: Optional[datetime]
    due_at: Optional[datetime]
    completed_at: Optional[datetime]

    risk_level: str
    risk_reason: Optional[str]
    risk_suggested_action: Optional[str]
    review_status: str

    trace_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class TaskListItem(BaseModel):
    """任务列表行（轻量字段）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    type: str
    status: str
    priority: str
    risk_level: str
    review_status: str
    assignee_id: int
    hospital_id: Optional[int]
    product_id: Optional[int]
    remind_at: Optional[datetime]
    due_at: Optional[datetime]
    created_at: datetime


class TaskListResponse(BaseModel):
    items: List[TaskListItem]
    total: int
    page: int
    page_size: int


# 显式导出 enum 给 schemas 包外使用
__all__ = [
    "TaskDraft",
    "TaskDetail",
    "TaskListItem",
    "TaskListResponse",
    "TaskType",
    "TaskStatus",
    "TaskPriority",
    "RiskLevel",
    "ReviewStatus",
    "BusinessObjectType",
]
