"""报告与图表模块 Pydantic 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# 趋势图
# ---------------------------------------------------------------------------

class TrendPoint(BaseModel):
    date: str          # "MM-DD"
    created: int
    completed: int
    overdue: int


class TrendResponse(BaseModel):
    points: List[TrendPoint]
    days: int


# ---------------------------------------------------------------------------
# 任务类型分布
# ---------------------------------------------------------------------------

class TypeDistItem(BaseModel):
    type: str
    label: str
    count: int
    pct: float         # 0-100，相对于最大值（方便渲染进度条）


class TypeDistResponse(BaseModel):
    items: List[TypeDistItem]
    total: int


# ---------------------------------------------------------------------------
# 风险分布
# ---------------------------------------------------------------------------

class RiskDistItem(BaseModel):
    level: str
    label: str
    count: int
    reviewed: int      # review_status 非 none/pending 的数量


class RiskDistResponse(BaseModel):
    items: List[RiskDistItem]
    total: int


# ---------------------------------------------------------------------------
# 负责人排行
# ---------------------------------------------------------------------------

class AssigneeRankItem(BaseModel):
    name: str
    total: int
    completed: int
    overdue: int
    completion_rate: int   # 0-100


class AssigneeRankResponse(BaseModel):
    items: List[AssigneeRankItem]


# ---------------------------------------------------------------------------
# 历史报告列表 / 详情
# ---------------------------------------------------------------------------

class ReportHistoryItem(BaseModel):
    id: int
    kind: str
    kind_label: str
    title: str
    preview: str       # 前 80 字内容摘要
    created_at: datetime
    status: str


class ReportHistoryResponse(BaseModel):
    items: List[ReportHistoryItem]
    total: int
    page: int
    page_size: int


class ReportDetail(BaseModel):
    id: int
    kind: str
    title: str
    content: str
    created_at: datetime
    status: str
