"""风险评估服务层：把 Risk Agent 的结果落到数据库。

职责：
- 调 `risk_agent.assess_risk` 拿 `RiskAssessment`。
- 写一条 `risk_records`，承载明细（关键词、规则、LLM 原文）。
- 反写 `tasks.risk_level / risk_reason / risk_suggested_action`，
  若 high / critical 还会把 `review_status=pending`、`status=awaiting_review`。
- 写 `task_events`：
    - 高风险 → `risk_review_request`
    - 否则   → `update`
该函数**假定调用方已在事务内**（由 endpoint 的 `async with session.begin()` 提供）。
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.risk_agent import assess_risk
from app.core.logger import get_logger
from app.models.enums import (
    ReviewStatus,
    RiskLevel,
    TaskEventType,
    TaskStatus,
)
from app.models.risk_record import RiskRecord
from app.models.task import Task
from app.models.task_event import TaskEvent
from app.schemas.risk import RiskAssessment
from app.schemas.task import TaskDraft

logger = get_logger(__name__)


_HIGH_LEVELS = {RiskLevel.HIGH.value, RiskLevel.CRITICAL.value}


async def evaluate_and_persist(
    session: AsyncSession,
    *,
    task: Task,
    draft: TaskDraft,
    trace_id: Optional[str] = None,
) -> RiskAssessment:
    """对已创建的任务做风险评估并落库，返回最终 RiskAssessment。"""
    assessment = await assess_risk(draft)
    await _persist(session, task=task, assessment=assessment, trace_id=trace_id)
    return assessment


async def _persist(
    session: AsyncSession,
    *,
    task: Task,
    assessment: RiskAssessment,
    trace_id: Optional[str],
) -> None:
    level_value = (
        assessment.level.value if hasattr(assessment.level, "value") else str(assessment.level)
    )
    requires_review = level_value in _HIGH_LEVELS

    task.risk_level = level_value
    task.risk_reason = assessment.reason
    task.risk_suggested_action = assessment.suggested_action

    review_status_value: str
    if requires_review:
        task.review_status = ReviewStatus.PENDING.value
        task.status = TaskStatus.AWAITING_REVIEW.value
        review_status_value = ReviewStatus.PENDING.value
    else:
        review_status_value = ReviewStatus.NONE.value

    record = RiskRecord(
        task_id=task.id,
        risk_level=level_value,
        reason=assessment.reason,
        suggested_action=assessment.suggested_action,
        keywords_hit=assessment.matched_keywords or None,
        rule_hit=assessment.rule_hits or None,
        llm_judgement=(assessment.llm.model_dump(mode="json") if assessment.llm else None),
        review_status=review_status_value,
        trace_id=trace_id,
    )
    session.add(record)

    event_type = (
        TaskEventType.RISK_REVIEW_REQUEST.value
        if requires_review
        else TaskEventType.UPDATE.value
    )
    session.add(
        TaskEvent(
            task_id=task.id,
            event_type=event_type,
            operator_id=None,
            operator_kind="agent",
            payload={
                "risk_level": level_value,
                "rules_level": (
                    assessment.rules_level.value
                    if hasattr(assessment.rules_level, "value")
                    else str(assessment.rules_level)
                ),
                "type_baseline": (
                    assessment.type_baseline.value
                    if hasattr(assessment.type_baseline, "value")
                    else str(assessment.type_baseline)
                ),
                "matched_keywords": assessment.matched_keywords,
                "rule_hits": assessment.rule_hits,
                "llm_failed": assessment.llm_failed,
                "requires_review": requires_review,
            },
            trace_id=trace_id,
        )
    )

    await session.flush()
    await session.refresh(task)
    logger.info(
        "risk assessed: task_id=%s level=%s review=%s trace_id=%s",
        task.id,
        level_value,
        requires_review,
        trace_id,
    )


__all__ = ["evaluate_and_persist"]
