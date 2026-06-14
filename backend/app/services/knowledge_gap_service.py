"""知识空缺任务服务（Phase 6）。

职责：
- 当 RAG 置信度低于阈值时，自动在 knowledge_gap_tasks 表写一条记录。
- 自动寻找合适的知识补充负责人（医学支持 > 产品运营 > 管理员）。
- 同时在对应的 tasks 表写一条 knowledge_maintain 类型的跟进任务（可选）。
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.rag_agent import RagAgentResult
from app.core.logger import get_logger
from app.models.enums import KnowledgeGapStatus, RoleCode
from app.models.knowledge_gap import KnowledgeGapTask
from app.models.user import Role, User, UserRole
from app.services.user_service import get_default_user

logger = get_logger(__name__)


async def create_gap_if_needed(
    session: AsyncSession,
    rag_result: RagAgentResult,
    *,
    source_task_id: Optional[int] = None,
    trace_id: Optional[str] = None,
) -> Optional[KnowledgeGapTask]:
    """若 rag_result.is_gap 为 True，创建 knowledge_gap_task 并返回；否则返回 None。

    调用方须已在事务内（由 endpoint 的 async with session.begin() 提供）。
    """
    if not rag_result.is_gap:
        return None

    assignee = await _find_knowledge_assignee(session)

    gap = KnowledgeGapTask(
        source_task_id=source_task_id,
        original_question=rag_result.question,
        retrieval_query=rag_result.question,
        confidence=rag_result.confidence,
        rag_hits_snapshot=rag_result.hits_snapshot() or None,
        assignee_id=assignee.id,
        status=KnowledgeGapStatus.OPEN.value,
        trace_id=trace_id,
    )
    session.add(gap)
    await session.flush()
    await session.refresh(gap)

    logger.info(
        "knowledge_gap created: id=%s question=%r confidence=%.2f assignee=%s",
        gap.id,
        rag_result.question[:60],
        rag_result.confidence,
        assignee.id,
    )
    return gap


async def _find_knowledge_assignee(session: AsyncSession) -> User:
    """按优先级找知识补充任务的负责人：医学支持 → 产品运营 → 管理员 → 第一个用户。"""
    for role_code in (
        RoleCode.MEDICAL_SUPPORT.value,
        RoleCode.PRODUCT_OPS.value,
        RoleCode.ADMIN.value,
    ):
        user = await _first_user_with_role(session, role_code)
        if user is not None:
            return user

    return await get_default_user(session)


async def _first_user_with_role(session: AsyncSession, role_code: str) -> Optional[User]:
    return (
        await session.execute(
            select(User)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                Role.code == role_code,
                User.deleted_at.is_(None),
                Role.deleted_at.is_(None),
            )
            .order_by(User.id)
            .limit(1)
        )
    ).scalar_one_or_none()


async def get_gap(session: AsyncSession, gap_id: int) -> Optional[KnowledgeGapTask]:
    return (
        await session.execute(
            select(KnowledgeGapTask).where(
                KnowledgeGapTask.id == gap_id,
                KnowledgeGapTask.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# 列表查询
# ---------------------------------------------------------------------------

async def list_gaps(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    assignee_id: Optional[int] = None,
    search: Optional[str] = None,
) -> tuple[list[KnowledgeGapTask], int]:
    """分页查询知识空缺任务列表。"""
    from sqlalchemy import func

    stmt = select(KnowledgeGapTask).where(KnowledgeGapTask.deleted_at.is_(None))

    if status:
        stmt = stmt.where(KnowledgeGapTask.status == status)
    if assignee_id:
        stmt = stmt.where(KnowledgeGapTask.assignee_id == assignee_id)
    if search:
        keyword = f"%{search.strip()}%"
        stmt = stmt.where(KnowledgeGapTask.original_question.like(keyword))

    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()

    rows = (
        await session.execute(
            stmt.order_by(KnowledgeGapTask.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return list(rows), total


# ---------------------------------------------------------------------------
# 处理（知识补充人提交）
# ---------------------------------------------------------------------------

async def process_gap(
    session: AsyncSession,
    gap_id: int,
    resolution_note: str,
    action: str,  # "save_draft" | "submit_review"
) -> KnowledgeGapTask:
    """处理知识空缺：保存草稿或提交审核。"""
    from app.core.exceptions import BizException

    gap = await get_gap(session, gap_id)
    if gap is None:
        raise BizException(code=4044, message=f"知识空缺任务 id={gap_id} 不存在")
    if gap.status == KnowledgeGapStatus.CLOSED.value:
        raise BizException(code=4001, message="该任务已归档，无法操作")

    gap.resolution_note = resolution_note
    gap.status = (
        KnowledgeGapStatus.IN_PROGRESS.value
        if action == "save_draft"
        else KnowledgeGapStatus.RESOLVED.value
    )
    await session.flush()
    await session.refresh(gap)
    logger.info("gap processed: id=%s status=%s", gap.id, gap.status)
    return gap


# ---------------------------------------------------------------------------
# 审核（主管决策）
# ---------------------------------------------------------------------------

async def review_gap(
    session: AsyncSession,
    gap_id: int,
    action: str,  # "approve" | "reject"
    comment: Optional[str] = None,
) -> KnowledgeGapTask:
    """审核知识空缺：通过（归档关闭）或驳回（退回重做）。"""
    from app.core.exceptions import BizException

    gap = await get_gap(session, gap_id)
    if gap is None:
        raise BizException(code=4044, message=f"知识空缺任务 id={gap_id} 不存在")
    if gap.status not in (KnowledgeGapStatus.RESOLVED.value, KnowledgeGapStatus.IN_PROGRESS.value):
        raise BizException(code=4001, message="只有已提交审核的任务才能进行审核")

    if action == "approve":
        gap.status = KnowledgeGapStatus.CLOSED.value
        if comment:
            gap.resolution_note = (gap.resolution_note or "") + f"\n[审核通过] {comment}"
    else:
        gap.status = KnowledgeGapStatus.OPEN.value
        if comment:
            gap.resolution_note = (gap.resolution_note or "") + f"\n[审核驳回] {comment}"

    await session.flush()
    await session.refresh(gap)
    logger.info("gap reviewed: id=%s action=%s status=%s", gap.id, action, gap.status)
    return gap


# ---------------------------------------------------------------------------
# 归档
# ---------------------------------------------------------------------------

async def archive_gap(session: AsyncSession, gap_id: int) -> KnowledgeGapTask:
    """手动归档知识空缺任务（直接关闭）。"""
    from app.core.exceptions import BizException
    from datetime import datetime, timezone

    gap = await get_gap(session, gap_id)
    if gap is None:
        raise BizException(code=4044, message=f"知识空缺任务 id={gap_id} 不存在")

    gap.status = KnowledgeGapStatus.CLOSED.value
    await session.flush()
    await session.refresh(gap)
    return gap


__all__ = [
    "create_gap_if_needed",
    "get_gap",
    "list_gaps",
    "process_gap",
    "review_gap",
    "archive_gap",
]
