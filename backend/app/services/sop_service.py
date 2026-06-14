"""SOP 文档服务层。

提供 SOP 文档的列表查询、详情、创建、更新、版本发布和归档操作。
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizException
from app.core.logger import get_logger
from app.models.enums import KnowledgeGapStatus
from app.models.knowledge_gap import KnowledgeGapTask
from app.models.sop_document import SopDocument
from app.schemas.knowledge import SopCreateRequest, SopNewVersionRequest, SopUpdateRequest

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------

async def get_knowledge_stats(session: AsyncSession) -> dict:
    """返回知识库总览统计数字。"""

    def _count(filters):
        return select(func.count(SopDocument.id)).where(*filters)

    sop_total = (
        await session.execute(
            _count([SopDocument.deleted_at.is_(None)])
        )
    ).scalar_one()
    sop_active = (
        await session.execute(
            _count([SopDocument.deleted_at.is_(None), SopDocument.status == "active"])
        )
    ).scalar_one()
    sop_draft = (
        await session.execute(
            _count([SopDocument.deleted_at.is_(None), SopDocument.status == "draft"])
        )
    ).scalar_one()

    gap_open = (
        await session.execute(
            select(func.count(KnowledgeGapTask.id)).where(
                KnowledgeGapTask.deleted_at.is_(None),
                KnowledgeGapTask.status == KnowledgeGapStatus.OPEN.value,
            )
        )
    ).scalar_one()
    gap_in_progress = (
        await session.execute(
            select(func.count(KnowledgeGapTask.id)).where(
                KnowledgeGapTask.deleted_at.is_(None),
                KnowledgeGapTask.status == KnowledgeGapStatus.IN_PROGRESS.value,
            )
        )
    ).scalar_one()
    gap_resolved = (
        await session.execute(
            select(func.count(KnowledgeGapTask.id)).where(
                KnowledgeGapTask.deleted_at.is_(None),
                KnowledgeGapTask.status == KnowledgeGapStatus.RESOLVED.value,
            )
        )
    ).scalar_one()

    recent_hits = (
        await session.execute(
            select(func.coalesce(func.sum(SopDocument.hit_count), 0)).where(
                SopDocument.deleted_at.is_(None),
                SopDocument.status == "active",
            )
        )
    ).scalar_one()

    return {
        "sop_total": sop_total,
        "sop_active": sop_active,
        "sop_draft": sop_draft,
        "gap_open": gap_open,
        "gap_in_progress": gap_in_progress,
        "gap_resolved": gap_resolved,
        "recent_30d_hits": recent_hits,
    }


# ---------------------------------------------------------------------------
# SOP 列表与详情
# ---------------------------------------------------------------------------

async def list_sops(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
) -> tuple[list[SopDocument], int]:
    """分页查询 SOP 列表（不含历史 archived 版本，除非显式传 status=archived）。"""
    stmt = select(SopDocument).where(SopDocument.deleted_at.is_(None))

    # 默认不显示历史版本；前端传 status=archived 才显示
    if status:
        stmt = stmt.where(SopDocument.status == status)
    else:
        stmt = stmt.where(SopDocument.status.in_(["active", "draft"]))

    if search:
        keyword = f"%{search.strip()}%"
        stmt = stmt.where(
            SopDocument.title.like(keyword)
            | SopDocument.code.like(keyword)
            | SopDocument.category.like(keyword)
        )
    if category:
        stmt = stmt.where(SopDocument.category == category)

    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()

    rows = (
        await session.execute(
            stmt.order_by(SopDocument.category.asc(), SopDocument.code.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return list(rows), total


async def get_sop(session: AsyncSession, sop_id: int) -> Optional[SopDocument]:
    return (
        await session.execute(
            select(SopDocument).where(
                SopDocument.id == sop_id,
                SopDocument.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def get_sop_categories(session: AsyncSession) -> list[str]:
    """返回所有不重复的 SOP 类别（用于前端筛选下拉）。"""
    rows = (
        await session.execute(
            select(SopDocument.category)
            .where(SopDocument.deleted_at.is_(None), SopDocument.category.isnot(None))
            .distinct()
            .order_by(SopDocument.category)
        )
    ).scalars().all()
    return list(rows)


# ---------------------------------------------------------------------------
# SOP 创建
# ---------------------------------------------------------------------------

async def create_sop(
    session: AsyncSession,
    req: SopCreateRequest,
    created_by: Optional[int] = None,
) -> SopDocument:
    """创建 SOP 文档。同一 code 可多次创建（不同版本），但 active 版本只能有一个。"""
    # 若 status=active，先将同 code 下已有的 active 版本降为 archived
    if req.status == "active":
        await _archive_active_by_code(session, req.code)

    doc = SopDocument(
        code=req.code,
        title=req.title,
        category=req.category,
        department=req.department,
        version=req.version,
        tags=req.tags or [],
        content=req.content,
        status=req.status,
        created_by=created_by,
    )
    session.add(doc)
    await session.flush()
    await session.refresh(doc)
    logger.info("sop created: id=%s code=%s version=%s", doc.id, doc.code, doc.version)
    return doc


# ---------------------------------------------------------------------------
# SOP 更新
# ---------------------------------------------------------------------------

async def update_sop(
    session: AsyncSession,
    sop_id: int,
    req: SopUpdateRequest,
) -> SopDocument:
    doc = await get_sop(session, sop_id)
    if doc is None:
        raise BizException(code=4044, message=f"SOP id={sop_id} 不存在")

    if req.title is not None:
        doc.title = req.title
    if req.category is not None:
        doc.category = req.category
    if req.department is not None:
        doc.department = req.department
    if req.tags is not None:
        doc.tags = req.tags
    if req.content is not None:
        doc.content = req.content
    if req.status is not None:
        # 若升级为 active，先归档同 code 下其他 active 版本
        if req.status == "active" and doc.status != "active":
            await _archive_active_by_code(session, doc.code, exclude_id=sop_id)
        doc.status = req.status

    await session.flush()
    await session.refresh(doc)
    return doc


# ---------------------------------------------------------------------------
# 发布新版本
# ---------------------------------------------------------------------------

async def create_new_version(
    session: AsyncSession,
    sop_id: int,
    req: SopNewVersionRequest,
    created_by: Optional[int] = None,
) -> SopDocument:
    """基于现有 SOP 发布新版本：旧版本归档，新版本激活。"""
    old_doc = await get_sop(session, sop_id)
    if old_doc is None:
        raise BizException(code=4044, message=f"SOP id={sop_id} 不存在")

    # 归档旧版本
    old_doc.status = "archived"

    new_doc = SopDocument(
        code=old_doc.code,
        title=old_doc.title,
        category=old_doc.category,
        department=old_doc.department,
        version=req.version,
        tags=old_doc.tags,
        content=req.content if req.content is not None else old_doc.content,
        status="active",
        created_by=created_by,
        parent_id=old_doc.id,
    )
    session.add(new_doc)
    await session.flush()
    await session.refresh(new_doc)
    logger.info(
        "sop new version: old_id=%s new_id=%s version=%s",
        sop_id, new_doc.id, req.version,
    )
    return new_doc


# ---------------------------------------------------------------------------
# 归档 SOP
# ---------------------------------------------------------------------------

async def archive_sop(session: AsyncSession, sop_id: int) -> SopDocument:
    doc = await get_sop(session, sop_id)
    if doc is None:
        raise BizException(code=4044, message=f"SOP id={sop_id} 不存在")
    doc.status = "archived"
    await session.flush()
    await session.refresh(doc)
    return doc


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

async def _archive_active_by_code(
    session: AsyncSession, code: str, exclude_id: Optional[int] = None
) -> None:
    """将某 code 下的所有 active 版本降为 archived。"""
    stmt = select(SopDocument).where(
        SopDocument.code == code,
        SopDocument.status == "active",
        SopDocument.deleted_at.is_(None),
    )
    if exclude_id is not None:
        stmt = stmt.where(SopDocument.id != exclude_id)
    docs = (await session.execute(stmt)).scalars().all()
    for doc in docs:
        doc.status = "archived"
    if docs:
        await session.flush()
