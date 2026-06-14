"""风险评估相关 Pydantic 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import RiskLevel


# ---------------------------------------------------------------------------
# 内部 / Agent 用
# ---------------------------------------------------------------------------

class LLMRiskJudgement(BaseModel):
    """LLM 层原始输出。"""

    model_config = ConfigDict(use_enum_values=True)

    level: RiskLevel
    reason: str = ""
    suggested_action: str = ""
    confidence: float = 0.5
    signals: List[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    """Risk Agent 的最终评估结果（仲裁后）。"""

    model_config = ConfigDict(use_enum_values=True)

    level: RiskLevel = Field(..., description="最终风险等级（规则与 LLM 取高）")
    reason: str = Field(..., description="风险原因（规则 + LLM 拼接）")
    suggested_action: str = Field(default="", description="建议处理动作")
    requires_review: bool = Field(default=False, description="是否需要人工审核")

    rules_level: RiskLevel = Field(..., description="规则层等级")
    type_baseline: RiskLevel = Field(..., description="任务类型基线等级")
    matched_keywords: List[str] = Field(default_factory=list)
    rule_hits: List[str] = Field(default_factory=list)

    llm: Optional[LLMRiskJudgement] = None
    llm_failed: bool = False


# ---------------------------------------------------------------------------
# 风险记录对外响应
# ---------------------------------------------------------------------------

class RiskRecordOut(BaseModel):
    """risk_records 表的对外响应模型。"""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: int
    task_id: int
    risk_level: str
    reason: Optional[str]
    suggested_action: Optional[str]
    keywords_hit: Optional[list]
    rule_hit: Optional[list]
    llm_judgement: Optional[dict]
    review_status: str
    reviewer_id: Optional[int]
    reviewed_at: Optional[datetime]
    review_comment: Optional[str]
    trace_id: Optional[str]
    created_at: datetime


class RiskRecordListResponse(BaseModel):
    items: List[RiskRecordOut]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# 风险统计
# ---------------------------------------------------------------------------

class RiskStats(BaseModel):
    """首页指标卡数据。"""

    pending_count: int = Field(description="待审核任务数")
    critical_count: int = Field(description="紧急风险任务数")
    escalated_count: int = Field(description="升级中工单数")
    high_count: int = Field(description="高风险任务数")
    approved_today: int = Field(description="今日已审核通过数")


# ---------------------------------------------------------------------------
# 风险工单（escalated 任务）
# ---------------------------------------------------------------------------

class RiskTicketItem(BaseModel):
    """风险工单列表行。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    type: str
    risk_level: str
    review_status: str
    assignee_id: int
    hospital_id: Optional[int]
    product_id: Optional[int]
    due_at: Optional[datetime]
    created_at: datetime
    reviewed_at: Optional[datetime]
    review_comment: Optional[str]
    reviewer_id: Optional[int]


class RiskTicketListResponse(BaseModel):
    items: List[RiskTicketItem]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# 风险规则
# ---------------------------------------------------------------------------

class RiskRuleOut(BaseModel):
    """risk_rules 表的对外响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str]
    rule_type: str
    keywords: Optional[list]
    task_types: Optional[list]
    baseline_level: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class RiskRuleCreateRequest(BaseModel):
    """POST /risk/rules 请求体。"""

    name: str = Field(..., min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, max_length=500)
    rule_type: Literal["keyword", "type_baseline", "composite"] = "keyword"
    keywords: List[str] = Field(default_factory=list)
    task_types: List[str] = Field(default_factory=list)
    baseline_level: Literal["low", "medium", "high", "critical"] = "medium"
    is_active: bool = True


class RiskRuleUpdateRequest(BaseModel):
    """PATCH /risk/rules/{id} 请求体（部分更新）。"""

    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    description: Optional[str] = None
    keywords: Optional[List[str]] = None
    task_types: Optional[List[str]] = None
    baseline_level: Optional[Literal["low", "medium", "high", "critical"]] = None
    is_active: Optional[bool] = None


class RiskRuleListResponse(BaseModel):
    items: List[RiskRuleOut]
    total: int


__all__ = [
    "LLMRiskJudgement",
    "RiskAssessment",
    "RiskRecordOut",
    "RiskRecordListResponse",
    "RiskStats",
    "RiskTicketItem",
    "RiskTicketListResponse",
    "RiskRuleOut",
    "RiskRuleCreateRequest",
    "RiskRuleUpdateRequest",
    "RiskRuleListResponse",
]
