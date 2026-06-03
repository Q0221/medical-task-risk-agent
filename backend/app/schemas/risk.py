"""风险评估相关 Pydantic 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import RiskLevel


class LLMRiskJudgement(BaseModel):
    """LLM 层原始输出（校验通过后落到 risk_records.llm_judgement）。"""

    model_config = ConfigDict(use_enum_values=True)

    level: RiskLevel
    reason: str = ""
    suggested_action: str = ""
    confidence: float = 0.5
    signals: List[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    """Risk Agent 的最终评估结果（仲裁后）。

    既会在 API 响应中返回给前端，也会被 risk_service 拆开写到
    `tasks` + `risk_records`。
    """

    model_config = ConfigDict(use_enum_values=True)

    level: RiskLevel = Field(..., description="最终风险等级（规则与 LLM 取高）")
    reason: str = Field(..., description="风险原因（规则 + LLM 拼接）")
    suggested_action: str = Field(default="", description="建议处理动作")
    requires_review: bool = Field(
        default=False, description="是否需要 Human-in-the-loop 审核"
    )

    rules_level: RiskLevel = Field(..., description="规则层（关键词 + 类型基线）等级")
    type_baseline: RiskLevel = Field(..., description="任务类型基线等级")
    matched_keywords: List[str] = Field(
        default_factory=list, description="命中的风险关键词"
    )
    rule_hits: List[str] = Field(
        default_factory=list, description="命中的业务规则 ID（rule_xxx）"
    )

    llm: Optional[LLMRiskJudgement] = Field(
        default=None, description="LLM 层判定原文（mock / 异常时可能为 None）"
    )
    llm_failed: bool = Field(
        default=False, description="True 表示 LLM 调用或解析失败，仅用规则层兜底"
    )


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


__all__ = [
    "LLMRiskJudgement",
    "RiskAssessment",
    "RiskRecordOut",
]
