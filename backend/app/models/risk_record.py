"""风险审核记录。

每次 Risk Agent 触发的风险判定 + 可能的人工审核结果都落一条；
同一个 task 可以有多条（升级 / 复核场景）。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel
from app.models.enums import ReviewStatus, RiskLevel


class RiskRecord(BaseModel):
    __tablename__ = "risk_records"

    task_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    risk_level: Mapped[str] = mapped_column(
        String(16), nullable=False, default=RiskLevel.LOW.value, index=True
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="风险原因摘要")
    suggested_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    keywords_hit: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="命中的关键词"
    )
    rule_hit: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="命中的业务规则 ID"
    )
    llm_judgement: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="LLM 风险判断原始输出"
    )

    review_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ReviewStatus.PENDING.value, index=True
    )
    reviewer_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    review_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
