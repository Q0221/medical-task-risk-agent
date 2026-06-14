"""风险记录 + 风险规则服务层。

职责：
- 查询 risk_records（列表、详情、按任务查询）
- 查询 tasks 中的风险工单（review_status=escalated）
- 风险统计数据（指标卡）
- 风险规则 CRUD
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizException
from app.core.logger import get_logger
from app.models.enums import ReviewStatus, RiskLevel, TaskStatus
from app.models.risk_record import RiskRecord
from app.models.risk_rule import RiskRule
from app.models.task import Task
from app.schemas.risk import RiskRuleCreateRequest, RiskRuleUpdateRequest

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 风险记录查询
# ---------------------------------------------------------------------------

async def list_risk_records(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    task_id: Optional[int] = None,
    risk_level: Optional[str] = None,
    review_status: Optional[str] = None,
) -> tuple[Sequence[RiskRecord], int]:
    page = max(1, page)
    page_size = max(1, min(100, page_size))

    base = select(RiskRecord).where(RiskRecord.deleted_at.is_(None))
    count_q = select(func.count()).select_from(RiskRecord).where(RiskRecord.deleted_at.is_(None))

    if task_id is not None:
        base = base.where(RiskRecord.task_id == task_id)
        count_q = count_q.where(RiskRecord.task_id == task_id)
    if risk_level:
        base = base.where(RiskRecord.risk_level == risk_level)
        count_q = count_q.where(RiskRecord.risk_level == risk_level)
    if review_status:
        base = base.where(RiskRecord.review_status == review_status)
        count_q = count_q.where(RiskRecord.review_status == review_status)

    items = (
        (
            await session.execute(
                base.order_by(RiskRecord.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    total = (await session.execute(count_q)).scalar_one()
    return items, int(total)


async def get_risk_record(session: AsyncSession, record_id: int) -> Optional[RiskRecord]:
    return (
        await session.execute(
            select(RiskRecord).where(
                RiskRecord.id == record_id,
                RiskRecord.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def list_records_by_task(
    session: AsyncSession, task_id: int
) -> Sequence[RiskRecord]:
    """返回某任务全部风险评估记录，按时间正序。"""
    items = (
        await session.execute(
            select(RiskRecord)
            .where(RiskRecord.task_id == task_id, RiskRecord.deleted_at.is_(None))
            .order_by(RiskRecord.created_at.asc())
        )
    ).scalars().all()
    return items


# ---------------------------------------------------------------------------
# 风险工单（escalated 任务）
# ---------------------------------------------------------------------------

async def list_risk_tickets(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    risk_level: Optional[str] = None,
) -> tuple[Sequence[Task], int]:
    """返回 review_status=escalated 的风险工单列表。"""
    page = max(1, page)
    page_size = max(1, min(100, page_size))

    base = select(Task).where(
        Task.review_status == ReviewStatus.ESCALATED.value,
        Task.deleted_at.is_(None),
    )
    count_q = select(func.count()).select_from(Task).where(
        Task.review_status == ReviewStatus.ESCALATED.value,
        Task.deleted_at.is_(None),
    )

    if risk_level:
        base = base.where(Task.risk_level == risk_level)
        count_q = count_q.where(Task.risk_level == risk_level)

    items = (
        (
            await session.execute(
                base.order_by(Task.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    total = (await session.execute(count_q)).scalar_one()
    return items, int(total)


# ---------------------------------------------------------------------------
# 风险统计（指标卡）
# ---------------------------------------------------------------------------

async def get_risk_stats(session: AsyncSession) -> dict:
    """汇总 RiskPage 顶部 4 张指标卡所需数据。"""
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=None
    )

    # 待审核（review_status=pending）
    pending_count = (
        await session.execute(
            select(func.count()).select_from(Task).where(
                Task.review_status == ReviewStatus.PENDING.value,
                Task.deleted_at.is_(None),
            )
        )
    ).scalar_one()

    # 紧急风险（risk_level=critical，未关闭）
    critical_count = (
        await session.execute(
            select(func.count()).select_from(Task).where(
                Task.risk_level == RiskLevel.CRITICAL.value,
                Task.status.not_in([TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value]),
                Task.deleted_at.is_(None),
            )
        )
    ).scalar_one()

    # 升级工单（review_status=escalated）
    escalated_count = (
        await session.execute(
            select(func.count()).select_from(Task).where(
                Task.review_status == ReviewStatus.ESCALATED.value,
                Task.deleted_at.is_(None),
            )
        )
    ).scalar_one()

    # 高风险（high，未关闭）
    high_count = (
        await session.execute(
            select(func.count()).select_from(Task).where(
                Task.risk_level == RiskLevel.HIGH.value,
                Task.status.not_in([TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value]),
                Task.deleted_at.is_(None),
            )
        )
    ).scalar_one()

    # 今日审核通过数
    approved_today = (
        await session.execute(
            select(func.count()).select_from(Task).where(
                Task.review_status == ReviewStatus.APPROVED.value,
                Task.reviewed_at >= today_start,
                Task.deleted_at.is_(None),
            )
        )
    ).scalar_one()

    return {
        "pending_count": int(pending_count),
        "critical_count": int(critical_count),
        "escalated_count": int(escalated_count),
        "high_count": int(high_count),
        "approved_today": int(approved_today),
    }


# ---------------------------------------------------------------------------
# 风险规则 CRUD
# ---------------------------------------------------------------------------

async def list_risk_rules(
    session: AsyncSession,
    *,
    include_inactive: bool = False,
) -> tuple[Sequence[RiskRule], int]:
    base = select(RiskRule).where(RiskRule.deleted_at.is_(None))
    if not include_inactive:
        base = base.where(RiskRule.is_active.is_(True))

    items = (
        await session.execute(base.order_by(RiskRule.created_at.asc()))
    ).scalars().all()
    return items, len(items)


async def get_risk_rule(session: AsyncSession, rule_id: int) -> Optional[RiskRule]:
    return (
        await session.execute(
            select(RiskRule).where(
                RiskRule.id == rule_id,
                RiskRule.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def create_risk_rule(
    session: AsyncSession,
    req: RiskRuleCreateRequest,
) -> RiskRule:
    rule = RiskRule(
        name=req.name,
        description=req.description,
        rule_type=req.rule_type,
        keywords=req.keywords or [],
        task_types=req.task_types or [],
        baseline_level=req.baseline_level,
        is_active=req.is_active,
    )
    session.add(rule)
    await session.flush()
    await session.refresh(rule)
    logger.info("risk rule created: id=%s name=%s", rule.id, rule.name)
    return rule


async def update_risk_rule(
    session: AsyncSession,
    rule_id: int,
    req: RiskRuleUpdateRequest,
) -> RiskRule:
    rule = await get_risk_rule(session, rule_id)
    if rule is None:
        raise BizException(code=4044, message=f"规则 id={rule_id} 不存在")

    if req.name is not None:
        rule.name = req.name
    if req.description is not None:
        rule.description = req.description
    if req.keywords is not None:
        rule.keywords = req.keywords
    if req.task_types is not None:
        rule.task_types = req.task_types
    if req.baseline_level is not None:
        rule.baseline_level = req.baseline_level
    if req.is_active is not None:
        rule.is_active = req.is_active

    await session.flush()
    await session.refresh(rule)
    logger.info("risk rule updated: id=%s", rule_id)
    return rule


async def delete_risk_rule(session: AsyncSession, rule_id: int) -> None:
    rule = await get_risk_rule(session, rule_id)
    if rule is None:
        raise BizException(code=4044, message=f"规则 id={rule_id} 不存在")

    rule.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await session.flush()
    logger.info("risk rule deleted: id=%s", rule_id)
