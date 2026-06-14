"""知识库接口。

已实现：
- POST /agent/knowledge              SOP 知识问答（原有，Phase 6）
- GET  /knowledge/stats              知识库总览统计
- GET  /knowledge/sop                SOP 文档列表（搜索、分类筛选、状态筛选、分页）
- GET  /knowledge/sop/categories     SOP 分类枚举值
- POST /knowledge/sop                创建 SOP 文档
- GET  /knowledge/sop/{id}           SOP 文档详情
- PATCH /knowledge/sop/{id}          更新 SOP 文档
- POST /knowledge/sop/{id}/version   发布新版本（旧版本自动归档）
- POST /knowledge/sop/{id}/archive   归档 SOP 文档
- GET  /knowledge/gaps               知识空缺任务列表
- GET  /knowledge/gaps/{id}          知识空缺任务详情
- PATCH /knowledge/gaps/{id}/process 处理（提交补充内容）
- PATCH /knowledge/gaps/{id}/review  审核（通过/驳回）
- POST /knowledge/gaps/{id}/archive  归档（直接关闭）
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.rag_agent import ask_knowledge
from app.api.deps import db_session, get_current_user, require_app_roles
from app.core.exceptions import BizException
from app.core.response import success
from app.schemas.knowledge import (
    GapActionResult,
    GapDetail,
    GapListItem,
    GapListResponse,
    GapProcessRequest,
    GapReviewRequest,
    KnowledgeStats,
    SopCreateRequest,
    SopDetail,
    SopListItem,
    SopListResponse,
    SopNewVersionRequest,
    SopUpdateRequest,
)
from app.schemas.rag import KnowledgeQueryRequest, RagResultOut
from app.services import knowledge_gap_service, sop_service
from app.services.auth_service import CurrentUser
from app.services.user_service import get_user_by_id

router = APIRouter(tags=["knowledge"])

# ============================================================================
# 原有 RAG 问答（Phase 6，保持原路径）
# ============================================================================

@router.post("/agent/knowledge", summary="SOP 知识问答（Phase 6）")
async def query_knowledge(
    body: KnowledgeQueryRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    """向企业知识库提问，获取 SOP 操作建议。

    - 置信度 ≥ 0.55：直接返回答案和参考文档。
    - 置信度 < 0.55：标记为知识空缺（`is_gap=true`），自动创建 knowledge_gap_task。
    """
    task_context: dict | None = None
    if body.task_id:
        from app.services.task_service import get_task
        task = await get_task(session, body.task_id)
        if task:
            task_context = {
                "type": task.type,
                "title": task.title,
                "description": task.description,
                "risk_level": task.risk_level,
                "risk_keywords": task.extra.get("risk_keywords", []) if task.extra else [],
            }

    rag_result = await ask_knowledge(body.question, task_context=task_context)

    gap_task_id: int | None = None
    if rag_result.is_gap:
        async with session.begin():
            gap = await knowledge_gap_service.create_gap_if_needed(
                session,
                rag_result,
                source_task_id=body.task_id,
            )
            if gap:
                gap_task_id = gap.id

    out = RagResultOut(
        question=rag_result.question,
        answer=rag_result.answer,
        confidence=rag_result.confidence,
        is_gap=rag_result.is_gap,
        gap_reason=rag_result.gap_reason,
        gap_task_id=gap_task_id,
        key_steps=rag_result.key_steps,
        references=rag_result.references,
        hits=[
            {"doc_id": h.doc_id, "title": h.title, "snippet": h.snippet, "score": h.score}
            for h in rag_result.hits
        ],
        used_builtin=rag_result.used_builtin,
    )
    return success(out.model_dump(mode="json"))


# ============================================================================
# 统计
# ============================================================================

@router.get("/knowledge/stats", summary="知识库总览统计")
async def get_stats(
    _: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    data = await sop_service.get_knowledge_stats(session)
    return success(KnowledgeStats(**data).model_dump())


# ============================================================================
# SOP 文档
# ============================================================================

@router.get("/knowledge/sop/categories", summary="SOP 分类枚举值")
async def get_sop_categories(
    _: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    categories = await sop_service.get_sop_categories(session)
    return success({"categories": categories})


@router.get("/knowledge/sop/{sop_id}", summary="SOP 文档详情")
async def get_sop_detail(
    sop_id: int = Path(..., ge=1),
    _: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    doc = await sop_service.get_sop(session, sop_id)
    if doc is None:
        raise BizException(code=4044, message=f"SOP id={sop_id} 不存在")
    return success(SopDetail.model_validate(doc).model_dump(mode="json"))


@router.get("/knowledge/sop", summary="SOP 文档列表")
async def list_sops(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None, description="active/draft/archived，默认返回 active+draft"),
    _: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    items, total = await sop_service.list_sops(
        session, page=page, page_size=page_size,
        search=search, category=category, status=status,
    )
    resp = SopListResponse(
        items=[SopListItem.model_validate(doc) for doc in items],
        total=total, page=page, page_size=page_size,
    )
    return success(resp.model_dump(mode="json"))


@router.post("/knowledge/sop", summary="创建 SOP 文档")
async def create_sop(
    body: SopCreateRequest,
    current_user: CurrentUser = Depends(require_app_roles("manager", "admin", "medical_support", "product_ops")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    async with session.begin():
        doc = await sop_service.create_sop(session, body, created_by=current_user.id)
    return success(SopDetail.model_validate(doc).model_dump(mode="json"))


@router.patch("/knowledge/sop/{sop_id}", summary="更新 SOP 文档")
async def update_sop(
    sop_id: int = Path(..., ge=1),
    body: SopUpdateRequest = ...,
    current_user: CurrentUser = Depends(require_app_roles("manager", "admin", "medical_support", "product_ops")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    async with session.begin():
        doc = await sop_service.update_sop(session, sop_id, body)
    return success(SopDetail.model_validate(doc).model_dump(mode="json"))


@router.post("/knowledge/sop/{sop_id}/version", summary="发布 SOP 新版本")
async def new_sop_version(
    sop_id: int = Path(..., ge=1),
    body: SopNewVersionRequest = ...,
    current_user: CurrentUser = Depends(require_app_roles("manager", "admin", "medical_support", "product_ops")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    """旧版本自动归档，新版本激活。"""
    async with session.begin():
        doc = await sop_service.create_new_version(session, sop_id, body, created_by=current_user.id)
    return success(SopDetail.model_validate(doc).model_dump(mode="json"))


@router.post("/knowledge/sop/{sop_id}/archive", summary="归档 SOP 文档")
async def archive_sop(
    sop_id: int = Path(..., ge=1),
    current_user: CurrentUser = Depends(require_app_roles("manager", "admin")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    async with session.begin():
        doc = await sop_service.archive_sop(session, sop_id)
    return success({"sop_id": sop_id, "status": doc.status, "message": "SOP 已归档"})


# ============================================================================
# 知识空缺任务
# ============================================================================

async def _enrich_gap(gap, session: AsyncSession) -> dict:
    """将 Gap ORM 行转为带 assignee_name 的 dict。"""
    assignee_name: str | None = None
    try:
        user = await get_user_by_id(session, gap.assignee_id)
        if user:
            assignee_name = user.name
    except Exception:
        pass
    data = {
        "id": gap.id,
        "original_question": gap.original_question,
        "confidence": gap.confidence,
        "status": gap.status,
        "assignee_id": gap.assignee_id,
        "assignee_name": assignee_name,
        "source_task_id": gap.source_task_id,
        "trace_id": gap.trace_id,
        "retrieval_query": getattr(gap, "retrieval_query", None),
        "rag_hits_snapshot": getattr(gap, "rag_hits_snapshot", None),
        "resolution_note": getattr(gap, "resolution_note", None),
        "created_at": gap.created_at,
        "updated_at": gap.updated_at,
    }
    return data


@router.get("/knowledge/gaps/{gap_id}", summary="知识空缺任务详情")
async def get_gap_detail(
    gap_id: int = Path(..., ge=1),
    _: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    gap = await knowledge_gap_service.get_gap(session, gap_id)
    if gap is None:
        raise BizException(code=4044, message=f"知识空缺任务 id={gap_id} 不存在")
    data = await _enrich_gap(gap, session)
    return success(GapDetail(**data).model_dump(mode="json"))


@router.get("/knowledge/gaps", summary="知识空缺任务列表")
async def list_gaps(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(default=None, description="open/in_progress/resolved/closed"),
    assignee_id: Optional[int] = Query(default=None, ge=1),
    search: Optional[str] = Query(default=None),
    _: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    items, total = await knowledge_gap_service.list_gaps(
        session, page=page, page_size=page_size,
        status=status, assignee_id=assignee_id, search=search,
    )

    enriched = []
    for gap in items:
        enriched.append(await _enrich_gap(gap, session))

    resp = GapListResponse(
        items=[GapListItem(**d) for d in enriched],
        total=total, page=page, page_size=page_size,
    )
    return success(resp.model_dump(mode="json"))


@router.patch("/knowledge/gaps/{gap_id}/process", summary="处理知识空缺（提交补充）")
async def process_gap(
    gap_id: int = Path(..., ge=1),
    body: GapProcessRequest = ...,
    _: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    """知识补充人填写 resolution_note，保存草稿或提交审核。"""
    async with session.begin():
        gap = await knowledge_gap_service.process_gap(
            session, gap_id,
            resolution_note=body.resolution_note,
            action=body.action,
        )
    return success(GapActionResult(
        gap_id=gap.id,
        status=gap.status,
        message="草稿已保存" if body.action == "save_draft" else "已提交审核",
    ).model_dump())


@router.patch("/knowledge/gaps/{gap_id}/review", summary="审核知识空缺")
async def review_gap(
    gap_id: int = Path(..., ge=1),
    body: GapReviewRequest = ...,
    _: CurrentUser = Depends(require_app_roles("manager", "admin")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    """主管审核：approve=归档关闭，reject=退回重做。"""
    async with session.begin():
        gap = await knowledge_gap_service.review_gap(
            session, gap_id,
            action=body.action,
            comment=body.comment,
        )
    return success(GapActionResult(
        gap_id=gap.id,
        status=gap.status,
        message="已审核通过并归档" if body.action == "approve" else "已驳回，退回重做",
    ).model_dump())


@router.post("/knowledge/gaps/{gap_id}/archive", summary="归档知识空缺任务")
async def archive_gap(
    gap_id: int = Path(..., ge=1),
    _: CurrentUser = Depends(require_app_roles("manager", "admin")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    async with session.begin():
        gap = await knowledge_gap_service.archive_gap(session, gap_id)
    return success(GapActionResult(
        gap_id=gap.id,
        status=gap.status,
        message="任务已归档",
    ).model_dump())
