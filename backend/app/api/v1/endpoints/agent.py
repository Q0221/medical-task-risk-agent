"""Agent 自然语言对话入口（Phase 9 — LangGraph 编排）。

POST /agent/chat         通过 LangGraph StateGraph 编排全流程。
POST /agent/confirm-draft 直接从草稿落库（跳过 LLM，用于草稿确认按钮）。
GET  /agent/candidates   模糊搜索负责人 / 医院 / 产品候选项。
GET  /agent/history/{id} 取回指定会话的历史消息。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from langchain_core.runnables import RunnableConfig
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_current_user, redis_client
from app.core.exceptions import BizException
from app.core.logger import get_logger
from app.core.response import success
from app.graph.builder import get_compiled_graph
from app.models.enums import RiskLevel, TaskType
from app.schemas.agent import (
    AgentChatRequest,
    AgentChatResponse,
    CandidateItem,
    CandidatesResponse,
    DraftConfirmRequest,
    HistoryMessage,
    SessionHistoryResponse,
)
from app.services.thinking_formatter import build_thinking_steps
from app.services.trace_service import get_traces
from app.schemas.rag import RagResultOut
from app.schemas.task import TaskDetail, TaskDraft
from app.services import knowledge_gap_service, risk_service, task_service
from app.services.auth_service import CurrentUser
from app.services.reminder_service import schedule_deadline, schedule_reminder
from app.services.session_service import append_history, get_history

router = APIRouter(prefix="/agent", tags=["agent"])
logger = get_logger(__name__)

_RAG_TRIGGER_LEVELS = {RiskLevel.MEDIUM.value, RiskLevel.HIGH.value, RiskLevel.CRITICAL.value}
_RAG_TRIGGER_TYPES = {"adverse_event", "device_anomaly", "complaint", "compliance_review"}


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _now_str() -> str:
    return datetime.now().strftime("%H:%M")


async def _attach_thinking_steps(response: dict, trace_id: Optional[str]) -> dict:
    """把本次请求的链路追踪附加到响应中。"""
    if not trace_id:
        return response
    try:
        traces = await get_traces(trace_id)
        steps = build_thinking_steps(traces)
        response["trace_id"] = trace_id
        response["thinking_steps"] = [
            step.model_dump(mode="json") for step in steps
        ]
    except Exception as exc:
        logger.warning("attach thinking steps failed trace_id=%s error=%s", trace_id, exc)
    return response


async def _save_pair(
    redis: Redis,
    session_id: str,
    user_text: str,
    agent_text: str,
    intent: Optional[str] = None,
    task_id: Optional[int] = None,
    is_error: bool = False,
) -> None:
    """将用户消息和 Agent 回复追加到会话历史。"""
    if not session_id or not redis:
        return
    now = _now_str()
    await append_history(redis, session_id, {
        "role": "user", "text": user_text, "time": now,
    })
    await append_history(redis, session_id, {
        "role": "agent", "text": agent_text, "time": now,
        "intent": intent, "task_id": task_id, "is_error": is_error,
    })


# ---------------------------------------------------------------------------
# POST /agent/chat
# ---------------------------------------------------------------------------

@router.post("/chat", summary="自然语言任务入口（LangGraph 编排，含意图识别 + 多轮追问）")
async def agent_chat(
    payload: AgentChatRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
    redis: Redis = Depends(redis_client),
) -> dict:
    trace_id = getattr(request.state, "trace_id", None)
    logger.info(
        "agent.chat trace_id=%s session_id=%s user_id=%s input=%r",
        trace_id, payload.session_id, current_user.id, payload.user_input,
    )

    initial_state = {
        "user_input": payload.user_input,
        "user_id": current_user.id,
        "session_id": payload.session_id,
        "trace_id": trace_id,
        "messages": [],
        "retry_count": 0,
        "should_rag": False,
        "risk_requires_review": False,
        "risk_llm_failed": False,
        "reminder_scheduled": False,
        "create_error": False,
    }

    graph_config = RunnableConfig(configurable={"session": session, "redis": redis})
    compiled_graph = get_compiled_graph()

    try:
        final_state = await compiled_graph.ainvoke(initial_state, config=graph_config)
    except BizException as exc:
        logger.warning("graph.ainvoke business error: code=%s message=%s", exc.code, exc.message)
        reply = _agent_error_reply(exc)
        resp = AgentChatResponse(intent="chitchat", reply=reply, messages=[reply])
        await _save_pair(redis, payload.session_id or "", payload.user_input, reply, is_error=True)
        return success(resp.model_dump(mode="json"))
    except Exception as exc:
        logger.exception("graph.ainvoke failed: %s", exc)
        reply = _agent_error_reply()
        resp = AgentChatResponse(intent="chitchat", reply=reply, messages=[])
        await _save_pair(redis, payload.session_id or "", payload.user_input, reply, is_error=True)
        return success(resp.model_dump(mode="json"))

    final_response = final_state.get("final_response")
    if final_response is None:
        logger.error("graph returned no final_response, state=%s", final_state)
        resp = AgentChatResponse(intent="chitchat", reply="处理完成，但无法生成响应", messages=[])
        return success(resp.model_dump(mode="json"))

    final_response = await _attach_thinking_steps(final_response, trace_id)

    # 保存历史
    intent_val = final_response.get("intent", "chitchat")
    agent_reply = _extract_reply_text(final_response)
    used_session_id = final_state.get("session_id") or payload.session_id or ""
    await _save_pair(
        redis, used_session_id, payload.user_input, agent_reply,
        intent=intent_val,
        task_id=final_response.get("task", {}).get("id") if final_response.get("task") else None,
        is_error=(intent_val == "create_error"),
    )

    return success(final_response)


def _extract_reply_text(resp: dict) -> str:
    if resp.get("question"):
        return resp["question"]
    if resp.get("reply"):
        return resp["reply"]
    if resp.get("error_message"):
        return resp["error_message"]
    if resp.get("messages"):
        return "\n".join(resp["messages"])
    return "已处理"


def _agent_error_reply(exc: BizException | None = None) -> str:
    if exc and exc.code in {4001, 4041, 4042, 4044, 4090}:
        return exc.message
    return "我没能完成解析，请重新描述任务，并明确具体任务、负责人和时间。"


# ---------------------------------------------------------------------------
# POST /agent/confirm-draft — 草稿确认（跳过 LLM，直接落库）
# ---------------------------------------------------------------------------

@router.post("/confirm-draft", summary="直接从草稿创建任务（跳过 LLM，用于前端确认按钮）")
async def confirm_draft(
    payload: DraftConfirmRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
    redis: Redis = Depends(redis_client),
) -> dict:
    trace_id = getattr(request.state, "trace_id", None)
    logger.info(
        "agent.confirm-draft trace_id=%s title=%r user_id=%s",
        trace_id, payload.title, current_user.id,
    )

    draft = TaskDraft(
        title=payload.title,
        type=payload.type,
        priority=payload.priority,
        description=payload.description,
        assignee_name=payload.assignee_name,
        hospital_name=payload.hospital_name,
        product_name=payload.product_name,
        business_object_type=payload.business_object_type,
        business_object_id=payload.business_object_id,
        due_at=payload.due_at,
        remind_at=payload.remind_at,
        risk_keywords=payload.risk_keywords or [],
    )

    # ── 创建任务 ──
    try:
        async with session.begin():
            task = await task_service.create_from_draft(
                session,
                draft,
                creator_user_id=current_user.id,
                trace_id=trace_id,
                agent_session_id=payload.session_id,
                resolved_assignee_id=payload.assignee_id,
                resolved_hospital_id=payload.hospital_id,
                resolved_product_id=payload.product_id,
            )
    except BizException as exc:
        # 负责人仍然找不到 → 返回可恢复错误 + 候选项
        candidates: dict = {}
        if exc.code == 4042 and payload.assignee_name:
            try:
                candidates["assignee"] = await task_service.find_user_candidates(
                    session, payload.assignee_name
                )
            except Exception:
                pass
        resp = AgentChatResponse(
            intent="create_error",
            is_recoverable=True,
            error_message=exc.message,
            draft=draft.model_dump(mode="json"),
            candidates=candidates,
            messages=[exc.message],
        )
        await _save_pair(
            redis, payload.session_id or "", f"确认草稿：{payload.title}",
            exc.message, intent="create_error", is_error=True,
        )
        return success(resp.model_dump(mode="json"))

    # ── 风险评估 ──
    assessment = None
    should_rag = False
    try:
        async with session.begin():
            task_obj = await task_service.get_task(session, task.id)
            assessment = await risk_service.evaluate_and_persist(
                session, task=task_obj, draft=draft, trace_id=trace_id,
            )
        level_val = assessment.level.value if hasattr(assessment.level, "value") else str(assessment.level)
        task_type = draft.type if isinstance(draft.type, str) else getattr(draft.type, "value", "other")
        should_rag = (level_val in _RAG_TRIGGER_LEVELS) or (task_type in _RAG_TRIGGER_TYPES)
    except Exception as exc:
        logger.warning("risk assessment failed in confirm-draft (non-fatal): %s", exc)

    # ── RAG 检索 ──
    rag_out: RagResultOut | None = None
    if should_rag:
        try:
            from app.agents.rag_agent import ask_knowledge
            task_ctx = {
                "type": task_type,
                "title": draft.title,
                "description": draft.description,
                "risk_level": level_val if assessment else None,
                "risk_keywords": draft.risk_keywords or [],
            }
            rag_result = await ask_knowledge(draft.title, task_context=task_ctx)
            if rag_result:
                gap_task_id: int | None = None
                if rag_result.is_gap:
                    try:
                        async with session.begin():
                            gap = await knowledge_gap_service.create_gap_if_needed(
                                session, rag_result,
                                source_task_id=task.id,
                                trace_id=trace_id,
                            )
                            if gap:
                                gap_task_id = gap.id
                    except Exception as gap_exc:
                        logger.warning("knowledge_gap creation failed (non-fatal): %s", gap_exc)
                rag_out = RagResultOut(
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
        except Exception as exc:
            logger.warning("rag in confirm-draft failed (non-fatal): %s", exc)

    # ── 提醒注册 ──
    try:
        if task.remind_at:
            await schedule_reminder(redis, task.id, task.remind_at)
        if task.due_at:
            await schedule_deadline(redis, task.id, task.due_at)
    except Exception as exc:
        logger.warning("remind in confirm-draft failed (non-fatal): %s", exc)

    # ── 重新加载最新 task 对象 ──
    async with session.begin():
        task_final = await task_service.get_task(session, task.id)
    task_detail = TaskDetail.model_validate(task_final)

    messages = [f"任务已创建：#{task.id}"]
    if assessment and assessment.requires_review:
        messages.append(f"风险等级 {assessment.level}，已转入人工审核")

    resp = AgentChatResponse(
        intent="create_todo",
        task=task_detail,
        draft=draft.model_dump(mode="json"),
        risk_assessment=assessment,
        rag_result=rag_out,
        messages=messages,
    )

    agent_reply = f"任务已创建：#{task.id} {draft.title}"
    await _save_pair(
        redis, payload.session_id or "", f"确认草稿：{payload.title}",
        agent_reply, intent="create_todo", task_id=task.id,
    )

    return success(resp.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# GET /agent/candidates — 名称候选项搜索
# ---------------------------------------------------------------------------

@router.get("/candidates", summary="模糊搜索负责人 / 医院 / 产品候选项")
async def search_candidates(
    entity_type: str = Query(..., description="搜索类型：user | hospital | product"),
    name: str = Query(..., min_length=1, max_length=50, description="关键词"),
    limit: int = Query(default=8, ge=1, le=20),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    if entity_type == "user":
        rows = await task_service.find_user_candidates(session, name, limit=limit)
    elif entity_type == "hospital":
        rows = await task_service.find_hospital_candidates(session, name, limit=limit)
    elif entity_type == "product":
        rows = await task_service.find_product_candidates(session, name, limit=limit)
    else:
        raise BizException(code=4001, message=f"不支持的搜索类型：{entity_type}")

    items = [CandidateItem(id=row["id"], name=row["name"], extra=row.get("extra")) for row in rows]
    resp = CandidatesResponse(entity_type=entity_type, query=name, items=items)
    return success(resp.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# GET /agent/thinking/{trace_id} — 思考过程
# ---------------------------------------------------------------------------

@router.get("/thinking/{trace_id}", summary="查看单次对话的思考过程")
async def get_thinking_process(
    trace_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    traces = await get_traces(trace_id)
    steps = build_thinking_steps(traces)
    return success({
        "trace_id": trace_id,
        "steps": [step.model_dump(mode="json") for step in steps],
    })


# ---------------------------------------------------------------------------
# GET /agent/history/{session_id} — 会话历史
# ---------------------------------------------------------------------------

@router.get("/history/{session_id}", summary="取回指定会话的历史消息")
async def get_session_history(
    session_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    redis: Redis = Depends(redis_client),
) -> dict:
    raw_messages = await get_history(redis, session_id)
    messages = []
    for item in raw_messages:
        messages.append(
            HistoryMessage(
                role=item.get("role", "agent"),
                text=item.get("text", ""),
                time=item.get("time", ""),
                intent=item.get("intent"),
                task_id=item.get("task_id"),
                is_error=item.get("is_error", False),
            )
        )
    resp = SessionHistoryResponse(session_id=session_id, messages=messages)
    return success(resp.model_dump(mode="json"))
