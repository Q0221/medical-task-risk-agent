"""Summary Pydantic 模式（Phase 10）。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TypeCountOut(BaseModel):
    type: str
    count: int


class AssigneeCountOut(BaseModel):
    assignee_id: int
    name: str
    total: int
    completed: int
    overdue: int


class TaskStatsOut(BaseModel):
    date_range: str
    total_created: int
    total_completed: int
    total_overdue: int
    total_cancelled: int
    total_high_risk: int
    total_pending_review: int
    total_knowledge_gap: int
    by_type: list[TypeCountOut]
    by_assignee: list[AssigneeCountOut]


class SummaryResponse(BaseModel):
    summary_type: str
    date_start: datetime
    date_end: datetime
    stats: TaskStatsOut
    narrative: str
    notification_id: Optional[int]
