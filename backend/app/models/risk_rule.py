"""风险规则配置表。

支持两类规则：
- keyword      : 关键词命中规则（title / description 包含关键词 → 触发）
- type_baseline: 任务类型基线规则（特定 task_type → 基线等级）

规则由 Risk Agent 读取，is_active=False 则跳过。
"""

from typing import Optional

from sqlalchemy import JSON, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class RiskRule(BaseModel):
    __tablename__ = "risk_rules"

    name: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="规则名称"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="规则说明"
    )
    rule_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="keyword",
        index=True,
        comment="keyword | type_baseline | composite",
    )
    keywords: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="命中关键词列表"
    )
    task_types: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="适用任务类型（空表示全部类型）"
    )
    baseline_level: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="medium",
        comment="命中后风险基线等级",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
        index=True,
        comment="是否启用",
    )
