"""业务档案模块 Pydantic 模型。

涵盖医院档案、产品档案的列表/详情/统计 Schema。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# 任务简要（档案详情页使用）
# ---------------------------------------------------------------------------

class TaskBrief(BaseModel):
    """嵌入档案详情的轻量任务行。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    type: str
    status: str
    risk_level: str
    priority: str
    assignee_id: int
    due_at: Optional[datetime] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# 医院档案
# ---------------------------------------------------------------------------

class HospitalListItem(BaseModel):
    """医院列表行：基础字段 + 聚合任务统计。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    level: Optional[str] = None
    region: Optional[str] = None
    risk_score: int
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    # 聚合计算字段（非 ORM 字段，由 Service 层注入）
    task_total: int = 0
    task_open: int = 0
    task_high_risk: int = 0
    latest_task_at: Optional[datetime] = None
    updated_at: datetime


class HospitalDetail(HospitalListItem):
    """医院详情：在列表字段基础上追加近期任务列表和关联产品名称列表。"""

    recent_tasks: List[TaskBrief] = []
    related_products: List[str] = []


class HospitalListResponse(BaseModel):
    items: List[HospitalListItem]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# 产品档案
# ---------------------------------------------------------------------------

class ProductListItem(BaseModel):
    """产品列表行：基础字段 + 聚合任务统计。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    category: Optional[str] = None
    business_unit: Optional[str] = None
    description: Optional[str] = None
    task_total: int = 0
    task_open: int = 0
    task_high_risk: int = 0
    latest_task_at: Optional[datetime] = None
    updated_at: datetime


class ProductDetail(ProductListItem):
    """产品详情：追加近期任务列表和关联医院名称列表。"""

    recent_tasks: List[TaskBrief] = []
    related_hospitals: List[str] = []


class ProductListResponse(BaseModel):
    items: List[ProductListItem]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# 档案总览统计
# ---------------------------------------------------------------------------

class RecordStats(BaseModel):
    """档案总览统计数据（页面顶部四个数字卡片）。"""

    hospital_count: int
    product_count: int
    risk_task_count: int          # 历史风险任务（risk_level in high/critical）
    high_risk_hospital_count: int  # 风险分 > 0 的医院数量
    open_task_count: int           # 当前未关闭任务总数
