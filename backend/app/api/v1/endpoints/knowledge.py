"""知识库问答接口（Phase 6）。

POST /agent/knowledge
  - 接收自然语言问题
  - 调 RAG Agent 检索 SOP + 生成回答
  - 置信度低时自动创建 knowledge_gap_task
  - 返回 RagResultOut（含答案、置信度、命中文档、gap 状态）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.rag_agent import ask_knowledge
from app.api.deps import db_session
from app.core.response import success
from app.schemas.rag import KnowledgeQueryRequest, RagResultOut
from app.services import knowledge_gap_service

router = APIRouter(prefix="/agent", tags=["knowledge"])


@router.post("/knowledge", summary="SOP 知识问答（Phase 6）")
async def query_knowledge(
    body: KnowledgeQueryRequest,
    session: AsyncSession = Depends(db_session),
) -> dict:
    """向企业知识库提问，获取 SOP 操作建议。

    - 置信度 ≥ 0.55：直接返回答案和参考文档。
    - 置信度 < 0.55：标记为知识空缺（`is_gap=true`），自动创建 knowledge_gap_task
      分派给医学支持或产品运营团队，并在响应中返回 `gap_task_id`。
    """
    # 构造任务上下文（可选，有 task_id 时可提升检索精度）
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
