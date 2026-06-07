"""LangGraph 节点实现（Phase 9）。

每个节点是一个 async 函数，签名为：
    async def node_name(state: AgentState, config: RunnableConfig) -> dict

返回值是对 state 的**增量更新**（LangGraph 会做 merge，不用返回完整 state）。

节点列表：
  supervisor_node  → 意图识别 / 判断是否多轮续接
  merge_node       → 合并多轮追问回答
  clarify_node     → 保存 pending draft 到 Redis，写 clarify 响应
  task_node        → 调用 task_service.create_from_draft
  risk_node        → 调用 risk_service.evaluate_and_persist
  rag_node         → 调用 ask_knowledge + knowledge_gap_service
  remind_node      → 调用 schedule_reminder / schedule_deadline
  done_node        → 组装最终 AgentChatResponse
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agents.rag_agent import RagAgentResult, ask_knowledge
from app.agents.task_agent import (
    ClarifyResult,
    IntentResult,
    TaskExtractionResult,
    extract_task,
    merge_clarification,
)
from app.core.logger import get_logger
from app.graph.state import AgentState
from app.models.enums import RiskLevel
from app.schemas.agent import AgentChatResponse
from app.schemas.rag import RagResultOut
from app.schemas.task import TaskDetail, TaskDraft
from app.services import knowledge_gap_service, risk_service, task_service
from app.services.reminder_service import schedule_deadline, schedule_reminder
from app.services.session_service import (
    PendingDraft,
    clear_session,
    generate_session_id,
    load_pending,
    save_pending,
)
from app.services.trace_service import NodeTracer

logger = get_logger(__name__)

# 触发 RAG 的条件（与 Phase 6 一致）
_RAG_TRIGGER_LEVELS = {RiskLevel.MEDIUM.value, RiskLevel.HIGH.value, RiskLevel.CRITICAL.value}
_RAG_TRIGGER_TYPES = {"adverse_event", "device_anomaly", "complaint", "compliance_review"}


# ---------------------------------------------------------------------------
# 工具：从 RunnableConfig 取资源
# ---------------------------------------------------------------------------

def _cfg(config: RunnableConfig) -> dict:
    return config.get("configurable", {})


def _clarify_message(draft_raw: dict, pending_field: str) -> str:
    fields = draft_raw.get("clarify_fields") if isinstance(draft_raw, dict) else None
    if not isinstance(fields, list) or not fields:
        fields = [pending_field]
    labels = []
    for field in fields:
        label = _clarify_field_label(str(field))
        if label not in labels:
            labels.append(label)
    return f"需要补充信息：{'、'.join(labels)}"


def _clarify_field_label(field: str) -> str:
    if field in ("title", "description"):
        return "具体任务内容"
    if field == "assignee_name":
        return "负责人"
    if field in ("due_at", "remind_at"):
        return "任务时间"
    return field


# ===========================================================================
# 1. Supervisor Node
# ===========================================================================

async def supervisor_node(state: AgentState, config: RunnableConfig) -> dict:
    """意图识别 + 路由决策。

    - 若 session_id 有待续接的 pending → route="merge"
    - 否则调用 extract_task LLM：
        ClarifyResult         → route="clarify"
        IntentResult(非任务)  → route="done"（直接回复）
        TaskExtractionResult  → route="create"
    """
    cfg = _cfg(config)
    redis = cfg.get("redis")
    trace_id = state.get("trace_id")
    session_id = state.get("session_id")

    async with NodeTracer(
        node="supervisor",
        trace_id=trace_id,
        session_id=session_id,
        input_data={"user_input": state.get("user_input"), "session_id": session_id},
    ) as tracer:
        # 检查多轮续接
        if session_id and redis:
            pending = await load_pending(redis, session_id)
            if pending is not None:
                tracer.output = {"route": "merge"}
                return {"route": "merge"}

        # 首轮：提取意图 + 草稿
        result = await extract_task(state["user_input"], user_id=state.get("user_id"))

        if isinstance(result, IntentResult):
            tracer.output = {"route": "done", "intent": result.intent, "reply": result.reply}
            return {
                "route": "done",
                "intent": result.intent,
                "reply": result.reply,
                "messages": [],
            }

        if isinstance(result, ClarifyResult):
            tracer.output = {"route": "clarify", "pending_field": result.pending_field}
            return {
                "route": "clarify",
                "intent": "create_task",
                "draft_raw": result.draft_raw,
                "pending_field": result.pending_field or "assignee_name",
                "pending_question": result.first_question,
                "retry_count": getattr(result, "retry_count", 0),
            }

        # TaskExtractionResult
        tracer.output = {"route": "create", "retry_count": result.retry_count}
        return {
            "route": "create",
            "intent": "create_task",
            "task_draft": result.draft.model_dump(mode="json"),
            "draft_raw": result.raw,
            "retry_count": result.retry_count,
        }


# ===========================================================================
# 2. Merge Node（多轮追问续接）
# ===========================================================================

async def merge_node(state: AgentState, config: RunnableConfig) -> dict:
    """加载 Redis pending，合并用户补充的字段值。"""
    cfg = _cfg(config)
    redis = cfg.get("redis")
    trace_id = state.get("trace_id")
    session_id = state.get("session_id")

    async with NodeTracer(
        node="merge",
        trace_id=trace_id,
        session_id=session_id,
        input_data={"session_id": session_id, "user_input": state.get("user_input")},
    ) as tracer:
        pending: PendingDraft = await load_pending(redis, session_id)
        effective_user_id = state.get("user_id") or (pending.user_id if pending else None)

        merged = await merge_clarification(
            draft_raw=pending.draft_raw,
            question=pending.pending_question,
            user_answer=state["user_input"],
            user_id=effective_user_id,
        )

        if isinstance(merged, ClarifyResult):
            tracer.output = {"route": "clarify", "pending_field": merged.pending_field}
            return {
                "route": "clarify",
                "draft_raw": merged.draft_raw,
                "pending_field": merged.pending_field or "assignee_name",
                "pending_question": merged.first_question,
                "retry_count": getattr(merged, "retry_count", 0),
            }

        # 字段完整，清除 pending
        await clear_session(redis, session_id)
        tracer.output = {"route": "create"}
        return {
            "route": "create",
            "task_draft": merged.draft.model_dump(mode="json"),
            "draft_raw": merged.raw,
            "retry_count": merged.retry_count,
        }


# ===========================================================================
# 3. Clarify Node
# ===========================================================================

async def clarify_node(state: AgentState, config: RunnableConfig) -> dict:
    """保存 pending draft 到 Redis，构建 need_clarify 响应。"""
    cfg = _cfg(config)
    redis = cfg.get("redis")
    trace_id = state.get("trace_id")
    session_id = state.get("session_id")
    pending_field = state.get("pending_field", "assignee_name")
    pending_question = state.get("pending_question", "请提供更多信息")
    draft_raw = state.get("draft_raw") or {}

    async with NodeTracer(
        node="clarify",
        trace_id=trace_id,
        session_id=session_id,
        input_data={"pending_field": pending_field, "pending_question": pending_question},
    ) as tracer:
        sid = session_id or generate_session_id()
        pending = PendingDraft(
            draft_raw=draft_raw,
            pending_field=pending_field,
            pending_question=pending_question,
            user_id=state.get("user_id"),
        )
        await save_pending(redis, sid, pending)

        resp = AgentChatResponse(
            intent="need_clarify",
            question=pending_question,
            session_id=sid,
            messages=[_clarify_message(draft_raw, pending_field)],
        )
        result = resp.model_dump(mode="json")
        tracer.output = {"session_id": sid, "pending_field": pending_field}
        return {"final_response": result, "session_id": sid}


# ===========================================================================
# 4. Task Node
# ===========================================================================

async def task_node(state: AgentState, config: RunnableConfig) -> dict:
    """将 TaskDraft 落库，写 task_created 通知。"""
    cfg = _cfg(config)
    session = cfg.get("session")
    trace_id = state.get("trace_id")
    session_id = state.get("session_id")
    draft_dict = state.get("task_draft") or {}

    async with NodeTracer(
        node="task_agent",
        trace_id=trace_id,
        session_id=session_id,
        input_data={"draft_title": draft_dict.get("title"), "user_id": state.get("user_id")},
    ) as tracer:
        draft = TaskDraft(**draft_dict)

        async with session.begin():
            task = await task_service.create_from_draft(
                session,
                draft,
                creator_user_id=state.get("user_id"),
                trace_id=trace_id,
                agent_session_id=session_id,
            )

        task_detail = TaskDetail.model_validate(task).model_dump(mode="json")
        tracer.output = {"task_id": task.id, "title": task.title}
        return {"task_id": task.id, "task_obj": task_detail, "messages": [f"任务已创建：id={task.id}"]}


# ===========================================================================
# 5. Risk Node
# ===========================================================================

async def risk_node(state: AgentState, config: RunnableConfig) -> dict:
    """风险评估并持久化 RiskRecord。"""
    cfg = _cfg(config)
    session = cfg.get("session")
    trace_id = state.get("trace_id")
    session_id = state.get("session_id")
    draft_dict = state.get("task_draft") or {}

    async with NodeTracer(
        node="risk_agent",
        trace_id=trace_id,
        session_id=session_id,
        input_data={"task_id": state.get("task_id")},
    ) as tracer:
        draft = TaskDraft(**draft_dict)
        task_obj = state.get("task_obj") or {}

        # 重新从 DB 读 task 并做风险评估，在同一事务内完成
        async with session.begin():
            task = await task_service.get_task(session, state["task_id"])
            assessment = await risk_service.evaluate_and_persist(
                session,
                task=task,
                draft=draft,
                trace_id=trace_id,
            )

        level_val = assessment.level.value if hasattr(assessment.level, "value") else str(assessment.level)
        task_type = draft_dict.get("type", "other")
        should_rag = (level_val in _RAG_TRIGGER_LEVELS) or (task_type in _RAG_TRIGGER_TYPES)

        messages = []
        if assessment.requires_review:
            messages.append(f"风险等级 {assessment.level}，已转入人工审核（review_status=pending）")
        elif assessment.llm_failed:
            messages.append("LLM 风险判定不可用，已使用规则层兜底")

        tracer.output = {
            "level": level_val,
            "requires_review": assessment.requires_review,
            "should_rag": should_rag,
        }
        return {
            "risk_level": level_val,
            "risk_requires_review": assessment.requires_review,
            "risk_llm_failed": assessment.llm_failed,
            "risk_assessment": assessment,
            "should_rag": should_rag,
            "messages": (state.get("messages") or []) + messages,
        }


# ===========================================================================
# 6. RAG Node
# ===========================================================================

async def rag_node(state: AgentState, config: RunnableConfig) -> dict:
    """调用 RAG Agent 检索 SOP 建议；若置信度低则创建 KnowledgeGap 任务。"""
    cfg = _cfg(config)
    session = cfg.get("session")
    trace_id = state.get("trace_id")
    session_id = state.get("session_id")
    draft_dict = state.get("task_draft") or {}

    async with NodeTracer(
        node="rag_agent",
        trace_id=trace_id,
        session_id=session_id,
        input_data={"task_id": state.get("task_id"), "risk_level": state.get("risk_level")},
    ) as tracer:
        task_ctx = {
            "type": draft_dict.get("type"),
            "title": draft_dict.get("title"),
            "description": draft_dict.get("description"),
            "risk_level": state.get("risk_level"),
            "risk_keywords": draft_dict.get("risk_keywords") or [],
        }
        rag_result: RagAgentResult = await ask_knowledge(
            draft_dict.get("title", ""), task_context=task_ctx
        )

        gap_task_id: int | None = None
        messages = list(state.get("messages") or [])

        if rag_result.is_gap:
            try:
                async with session.begin():
                    gap = await knowledge_gap_service.create_gap_if_needed(
                        session, rag_result,
                        source_task_id=state.get("task_id"),
                        trace_id=trace_id,
                    )
                    if gap:
                        gap_task_id = gap.id
                        messages.append(f"RAG 置信度低，已创建知识空缺任务：id={gap_task_id}")
            except Exception as exc:
                logger.warning("knowledge_gap creation failed (non-fatal): %s", exc)
        else:
            messages.append("已附加 SOP 操作建议")

        tracer.output = {
            "confidence": rag_result.confidence,
            "is_gap": rag_result.is_gap,
            "gap_task_id": gap_task_id,
        }
        return {"rag_result": rag_result, "gap_task_id": gap_task_id, "messages": messages}


# ===========================================================================
# 7. Remind Node
# ===========================================================================

async def remind_node(state: AgentState, config: RunnableConfig) -> dict:
    """若任务有 remind_at / due_at，则注册到 Redis ZSet。"""
    cfg = _cfg(config)
    redis = cfg.get("redis")
    trace_id = state.get("trace_id")
    session_id = state.get("session_id")
    task_obj = state.get("task_obj") or {}
    task_id = state.get("task_id")

    messages = list(state.get("messages") or [])

    async with NodeTracer(
        node="supervisor",  # remind 属于 supervisor 子步骤
        trace_id=trace_id,
        session_id=session_id,
        tool_name="schedule_reminder",
        input_data={"task_id": task_id},
    ) as tracer:
        remind_at = task_obj.get("remind_at")
        due_at = task_obj.get("due_at")
        scheduled = False
        try:
            if remind_at:
                from datetime import datetime
                dt = datetime.fromisoformat(remind_at) if isinstance(remind_at, str) else remind_at
                await schedule_reminder(redis, task_id, dt)
                messages.append(f"提醒已设置：{dt.strftime('%Y-%m-%d %H:%M')}")
                scheduled = True
            if due_at:
                from datetime import datetime
                dt = datetime.fromisoformat(due_at) if isinstance(due_at, str) else due_at
                await schedule_deadline(redis, task_id, dt)
        except Exception as exc:
            logger.warning("remind_node schedule failed (non-fatal): %s", exc)

        tracer.output = {"scheduled": scheduled}
        return {"reminder_scheduled": scheduled, "messages": messages}


# ===========================================================================
# 8. Done Node
# ===========================================================================

async def done_node(state: AgentState, config: RunnableConfig) -> dict:
    """组装最终 AgentChatResponse，写入 final_response。"""
    trace_id = state.get("trace_id")
    session_id = state.get("session_id")

    async with NodeTracer(
        node="supervisor",
        trace_id=trace_id,
        session_id=session_id,
        input_data={"intent": state.get("intent"), "task_id": state.get("task_id")},
    ) as tracer:
        intent = state.get("intent", "chitchat")

        # 非任务意图：直接回复
        if intent in ("chitchat", "query_task", "unclear") and not state.get("task_id"):
            _intent_map = {"chitchat": "chitchat", "query_task": "query_task", "unclear": "chitchat"}
            resp = AgentChatResponse(
                intent=_intent_map.get(intent, "chitchat"),
                reply=state.get("reply"),
                messages=[],
            )
            tracer.output = {"intent": resp.intent}
            return {"final_response": resp.model_dump(mode="json")}

        # 任务创建完成
        task_detail = None
        if state.get("task_obj"):
            try:
                from app.schemas.task import TaskDetail
                task_detail = TaskDetail(**state["task_obj"])
            except Exception:
                task_detail = None

        rag_out: RagResultOut | None = None
        rag_result = state.get("rag_result")
        if rag_result:
            try:
                rag_out = RagResultOut(
                    question=rag_result.question,
                    answer=rag_result.answer,
                    confidence=rag_result.confidence,
                    is_gap=rag_result.is_gap,
                    gap_reason=rag_result.gap_reason,
                    gap_task_id=state.get("gap_task_id"),
                    key_steps=rag_result.key_steps,
                    references=rag_result.references,
                    hits=[
                        {"doc_id": h.doc_id, "title": h.title, "snippet": h.snippet, "score": h.score}
                        for h in rag_result.hits
                    ],
                    used_builtin=rag_result.used_builtin,
                )
            except Exception as exc:
                logger.warning("rag_out build failed: %s", exc)

        resp = AgentChatResponse(
            intent="create_todo",
            task=task_detail,
            draft=state.get("draft_raw"),
            retry_count=state.get("retry_count", 0),
            risk_assessment=state.get("risk_assessment"),
            rag_result=rag_out,
            messages=state.get("messages") or [],
        )
        result = resp.model_dump(mode="json")
        tracer.output = {"intent": "create_todo", "task_id": state.get("task_id")}
        return {"final_response": result}
