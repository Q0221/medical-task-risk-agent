"""任务相关 Pydantic 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

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


class TaskCompleteRequest(BaseModel):
    """PATCH /tasks/{id}/complete 请求体。"""

    operator_id: Optional[int] = Field(default=None, description="操作人 user_id")
    comment: Optional[str] = Field(default=None, description="完成备注")


class TaskCancelRequest(BaseModel):
    """PATCH /tasks/{id}/cancel 请求体。"""

    operator_id: Optional[int] = Field(default=None, description="操作人 user_id")
    reason: Optional[str] = Field(default=None, description="取消原因")


class TaskAssignRequest(BaseModel):
    """PATCH /tasks/{id}/assign 请求体（assignee_id 和 assignee_name 二选一）。"""

    operator_id: Optional[int] = Field(default=None, description="操作人 user_id")
    assignee_id: Optional[int] = Field(default=None, description="新负责人 user_id")
    assignee_name: Optional[str] = Field(default=None, description="新负责人姓名（模糊匹配）")
    comment: Optional[str] = Field(default=None, description="分配备注")


class TaskRemindRequest(BaseModel):
    """POST /tasks/{id}/remind 请求体。"""

    remind_at: datetime = Field(..., description="新的提醒时间（ISO 8601 本地时间）")
    due_at: Optional[datetime] = Field(default=None, description="同时更新截止时间（可选）")


class TaskRemindResult(BaseModel):
    """POST /tasks/{id}/remind 响应体。"""

    task_id: int
    remind_at: datetime
    due_at: Optional[datetime]
    message: str


class TaskReviewRequest(BaseModel):
    """POST /tasks/{id}/review 请求体。"""

    action: Literal["approved", "rejected", "escalated"] = Field(
        ..., description="审核决定：approved=通过并放行, rejected=驳回并取消, escalated=升级上报"
    )
    reviewer_id: int = Field(..., ge=1, description="审核人 user_id")
    comment: Optional[str] = Field(default=None, max_length=1000, description="审核备注")


class TaskReviewResult(BaseModel):
    """POST /tasks/{id}/review 响应体（精简）。"""

    task_id: int
    review_status: str
    task_status: str
    reviewer_id: int
    reviewed_at: datetime
    message: str


class TaskEventOut(BaseModel):
    """任务事件（时间线条目）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    event_type: str
    operator_id: Optional[int]
    operator_kind: str
    payload: Optional[dict]
    created_at: datetime


class TaskTimelineResponse(BaseModel):
    items: List[TaskEventOut]
    total: int


class TaskCommentRequest(BaseModel):
    """POST /tasks/{id}/comments 请求体。"""

    content: str = Field(..., min_length=1, max_length=2000)


class TaskCommentOut(BaseModel):
    """评论响应（从 TaskEvent 中提取）。"""

    id: int
    task_id: int
    operator_id: Optional[int]
    operator_kind: str
    content: str
    created_at: datetime


class TaskAttachmentRequest(BaseModel):
    """POST /tasks/{id}/attachments 请求体（无实际文件存储，记元数据）。"""

    name: str = Field(..., min_length=1, max_length=255)
    url: Optional[str] = Field(default=None, max_length=1024)
    size: Optional[int] = Field(default=None, description="文件大小（字节）")


class TaskCollaboratorRequest(BaseModel):
    """PATCH /tasks/{id}/collaborators 请求体（覆盖写入）。"""

    user_ids: List[int] = Field(default_factory=list)


class TaskBatchCompleteRequest(BaseModel):
    """POST /tasks/batch/complete 请求体。"""

    task_ids: List[int] = Field(..., min_length=1, max_length=50)
    comment: Optional[str] = None


class TaskBatchCancelRequest(BaseModel):
    """POST /tasks/batch/cancel 请求体。"""

    task_ids: List[int] = Field(..., min_length=1, max_length=50)
    reason: Optional[str] = None


class TaskBatchAssignRequest(BaseModel):
    """POST /tasks/batch/assign 请求体（assignee_id 与 assignee_name 二选一）。"""

    task_ids: List[int] = Field(..., min_length=1, max_length=50)
    assignee_id: Optional[int] = None
    assignee_name: Optional[str] = None
    comment: Optional[str] = None


class TaskBatchResult(BaseModel):
    """批量操作响应。"""

    succeeded: List[int]
    failed: List[int]
    message: str


# 显式导出 enum 给 schemas 包外使用
__all__ = [
    "TaskDraft",
    "TaskDetail",
    "TaskListItem",
    "TaskListResponse",
    "TaskRemindRequest",
    "TaskRemindResult",
    "TaskReviewRequest",
    "TaskReviewResult",
    "TaskType",
    "TaskStatus",
    "TaskPriority",
    "RiskLevel",
    "ReviewStatus",
    "BusinessObjectType",
]
