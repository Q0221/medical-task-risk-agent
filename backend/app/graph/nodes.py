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
  summary_node     → 调用 run_summary 生成日报 / 周报
  done_node        → 组装最终 AgentChatResponse
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agents.rag_agent import RagAgentResult, ask_knowledge
from app.agents.summary_agent import TaskStats, run_summary
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
from app.schemas.agent import AgentChatResponse, QueryResult, QueryTaskItem
from app.schemas.rag import RagResultOut
from app.schemas.summary import AssigneeCountOut, SummaryResponse, TaskStatsOut, TypeCountOut
from app.schemas.task import TaskDetail, TaskDraft
from app.core.exceptions import BizException
from app.services import knowledge_gap_service, risk_service, task_service
from app.services.reminder_service import schedule_deadline, schedule_reminder
from app.services.user_service import find_user_by_name, get_user_by_id
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


_FULL_DATE_RE = re.compile(r"(20\d{2})[年/\-.](\d{1,2})[月/\-.](\d{1,2})[日号]?")
_MONTH_DAY_RE = re.compile(r"(?<!\d)(\d{1,2})月(\d{1,2})[日号]?")
_SHORT_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[\/\-.](\d{1,2})(?!\d)")
# "N天前" / "N天以前"，支持阿拉伯数字和一~三十的中文数字
_DAYS_AGO_RE = re.compile(r"([一二三四五六七八九十百\d]+)天(?:前|以前|之前)")
_CHINESE_NUM_MAP = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
    "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20,
    "二十一": 21, "二十二": 22, "二十三": 23, "二十四": 24, "二十五": 25,
    "二十六": 26, "二十七": 27, "二十八": 28, "二十九": 29, "三十": 30,
}
_SUMMARY_KEYWORDS = ("日报", "周报", "报告", "总结", "汇总")
_SUMMARY_ACTION_HINTS = ("生成", "出", "做", "查看", "看看", "看一下", "给我", "统计", "总结", "汇总")
_DAILY_HINTS = ("日报", "今天", "今日", "昨天", "昨日", "前天", "大前天")
_WEEKLY_HINTS = ("周报", "本周", "这周", "上周")
_QUERY_HINT_RE = re.compile(
    r"(查询|查一下|查看|有哪些|什么|列出|显示|我的).{0,12}(任务|待办|待处理)"
    r"|(任务|待办|待处理).{0,12}(查询|查|有哪些|什么)"
    r"|我的任务|我的待办|今日到期|今天到期|本周到期|已逾期",
)


def _utc_now_naive() -> datetime:
    """返回 UTC naive 时间，与数据库 datetime 字段比较保持一致。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _to_naive_utc(dt: datetime | None) -> datetime | None:
    """统一转为 naive UTC，避免 aware/naive 比较异常。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _looks_like_query(user_input: str) -> bool:
    text = user_input.strip()
    if not text:
        return False
    return bool(_QUERY_HINT_RE.search(text))


def _to_dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _parse_explicit_date(text: str, *, today: date) -> date | None:
    match = _FULL_DATE_RE.search(text)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        try:
            return date(year, month, day)
        except ValueError:
            return None

    match = _MONTH_DAY_RE.search(text) or _SHORT_DATE_RE.search(text)
    if not match:
        return None
    year = today.year
    month = int(match.group(1))
    day = int(match.group(2))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_summary_request(user_input: str, *, today: date | None = None) -> dict | None:
    """从自然语言中解析日报/周报生成请求。

    该规则在任务抽取前执行，避免“生成日报”被误识别为创建任务。
    """
    text = (user_input or "").strip()
    compact = re.sub(r"\s+", "", text)
    if not compact or not any(keyword in compact for keyword in _SUMMARY_KEYWORDS):
        return None

    has_daily_hint = any(hint in compact for hint in _DAILY_HINTS)
    has_weekly_hint = any(hint in compact for hint in _WEEKLY_HINTS)
    has_action_hint = any(hint in compact for hint in _SUMMARY_ACTION_HINTS)

    if has_weekly_hint:
        summary_type = "weekly"
    elif has_daily_hint:
        summary_type = "daily"
    elif has_action_hint:
        summary_type = "daily"
    else:
        return None

    today = today or date.today()
    explicit_date = _parse_explicit_date(compact, today=today)

    if summary_type == "daily":
        if explicit_date:
            target_date = explicit_date
        elif "大前天" in compact:
            target_date = today - timedelta(days=3)
        elif "前天" in compact:
            target_date = today - timedelta(days=2)
        elif "昨天" in compact or "昨日" in compact:
            target_date = today - timedelta(days=1)
        else:
            # 尝试解析 "N天前 / N天以前 / N天之前"
            days_ago_match = _DAYS_AGO_RE.search(compact)
            if days_ago_match:
                days_str = days_ago_match.group(1)
                if days_str.isdigit():
                    days_offset = int(days_str)
                else:
                    days_offset = _CHINESE_NUM_MAP.get(days_str, 0)
                target_date = today - timedelta(days=days_offset) if days_offset > 0 else today
            else:
                target_date = today
        date_start = _to_dt(target_date)
        date_end = date_start + timedelta(days=1)
    else:
        if explicit_date:
            week_start = explicit_date - timedelta(days=explicit_date.weekday())
        elif "上周" in compact:
            week_start = today - timedelta(days=today.weekday() + 7)
        else:
            week_start = today - timedelta(days=today.weekday())
        date_start = _to_dt(week_start)
        date_end = date_start + timedelta(days=7)

    return {
        "summary_type": summary_type,
        "date_start": date_start,
        "date_end": date_end,
    }


def _summary_trace_payload(req: dict) -> dict:
    return {
        "summary_type": req.get("summary_type"),
        "date_start": req.get("date_start").isoformat() if req.get("date_start") else None,
        "date_end": req.get("date_end").isoformat() if req.get("date_end") else None,
    }


def _stats_to_out(stats: TaskStats) -> TaskStatsOut:
    return TaskStatsOut(
        date_range=stats.date_range,
        total_created=stats.total_created,
        total_completed=stats.total_completed,
        total_overdue=stats.total_overdue,
        total_cancelled=stats.total_cancelled,
        total_high_risk=stats.total_high_risk,
        total_pending_review=stats.total_pending_review,
        total_knowledge_gap=stats.total_knowledge_gap,
        by_type=[TypeCountOut(type=item.type, count=item.count) for item in stats.by_type],
        by_assignee=[
            AssigneeCountOut(
                assignee_id=item.assignee_id,
                name=item.name,
                total=item.total,
                completed=item.completed,
                overdue=item.overdue,
            )
            for item in stats.by_assignee
        ],
    )


def _summary_reply(resp: SummaryResponse) -> str:
    period = "日报" if resp.summary_type == "daily" else "周报"
    return f"{period}已生成，统计区间：{resp.stats.date_range}。"


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
        summary_request = _parse_summary_request(state.get("user_input") or "")
        if summary_request:
            tracer.output = {"route": "summary", **_summary_trace_payload(summary_request)}
            return {
                "route": "summary",
                "intent": "generate_summary",
                "summary_request": summary_request,
            }

        user_input = state.get("user_input") or ""
        is_query_like = _looks_like_query(user_input)

        # 查询类输入不走 merge，避免把查询语句误当成追问回答
        if session_id and redis and is_query_like:
            await clear_session(redis, session_id)

        # 检查多轮续接
        if session_id and redis and not is_query_like:
            pending = await load_pending(redis, session_id)
            if pending is not None:
                tracer.output = {"route": "merge"}
                return {"route": "merge"}

        # 首轮：提取意图 + 草稿
        result = await extract_task(state["user_input"], user_id=state.get("user_id"))

        if isinstance(result, IntentResult):
            if result.intent == "query_task":
                # 将 LLM 输出的查询参数传入状态，路由到 query_node
                raw = result.raw_params
                query_params = {
                    "query_assignee": raw.get("query_assignee"),
                    "query_mine": bool(raw.get("query_mine")),
                    "query_status": raw.get("query_status"),
                    "query_risk": raw.get("query_risk"),
                    "query_overdue": bool(raw.get("query_overdue")),
                    "query_due_today": bool(raw.get("query_due_today")),
                    "query_due_this_week": bool(raw.get("query_due_this_week")),
                    "query_limit": min(int(raw.get("query_limit") or 10), 20),
                }
                tracer.output = {"route": "query", "query_params": query_params}
                return {
                    "route": "query",
                    "intent": "query_task",
                    "reply": result.reply,
                    "query_params": query_params,
                }
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
    """将 TaskDraft 落库，写 task_created 通知。

    负责人名称解析失败（BizException 4042）时，搜索候选人列表并返回
    可恢复错误响应（create_error=True），跳过后续 risk/rag/remind 节点。
    """
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

        try:
            async with session.begin():
                task = await task_service.create_from_draft(
                    session,
                    draft,
                    creator_user_id=state.get("user_id"),
                    trace_id=trace_id,
                    agent_session_id=session_id,
                )
        except BizException as exc:
            # 负责人找不到：搜索候选项，返回可恢复错误，保留草稿供前端编辑重提
            if exc.code == 4042:
                candidates: dict = {}
                try:
                    # 不使用 session.begin()：rollback 后直接 execute，SQLAlchemy autobegin 自动开启新事务
                    user_cands = await task_service.find_user_candidates(
                        session, draft_dict.get("assignee_name", "")
                    )
                    candidates["assignee"] = user_cands
                    if draft_dict.get("hospital_name"):
                        hospital_cands = await task_service.find_hospital_candidates(
                            session, draft_dict["hospital_name"]
                        )
                        candidates["hospital"] = hospital_cands
                except Exception as search_exc:
                    logger.warning("candidate search failed (non-fatal): %s", search_exc)

                resp = AgentChatResponse(
                    intent="create_error",
                    is_recoverable=True,
                    error_message=exc.message,
                    draft=draft_dict,
                    candidates=candidates,
                    messages=[exc.message],
                )
                tracer.output = {"error": exc.message, "candidates_count": len(candidates)}
                return {
                    "create_error": True,
                    "error_candidates": candidates,
                    "final_response": resp.model_dump(mode="json"),
                }
            raise

        task_detail = TaskDetail.model_validate(task).model_dump(mode="json")
        tracer.output = {"task_id": task.id, "title": task.title}
        return {"task_id": task.id, "task_obj": task_detail, "messages": [f"任务已创建：id={task.id}"]}


# ===========================================================================
# 5. Risk Node
# ===========================================================================

async def risk_node(state: AgentState, config: RunnableConfig) -> dict:
    """风险评估并持久化 RiskRecord。"""
    # 任务创建失败时跳过，final_response 已在 task_node 写入
    if state.get("create_error"):
        return {}

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
    if state.get("create_error"):
        return {}

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
    if state.get("create_error"):
        return {}

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
# 8. Summary Node
# ===========================================================================

async def summary_node(state: AgentState, config: RunnableConfig) -> dict:
    """调用 Summary Agent 生成日报/周报，并组装最终响应。"""
    cfg = _cfg(config)
    session = cfg.get("session")
    trace_id = state.get("trace_id")
    session_id = state.get("session_id")
    req = state.get("summary_request") or {}

    async with NodeTracer(
        node="summary_agent",
        trace_id=trace_id,
        session_id=session_id,
        input_data=_summary_trace_payload(req) if req else {},
    ) as tracer:
        if not req:
            reply = "请说明要生成日报还是周报，例如：生成今日日报、生成本周周报。"
            resp = AgentChatResponse(intent="chitchat", reply=reply, messages=[reply])
            tracer.output = {"status": "missing_summary_request"}
            return {"final_response": resp.model_dump(mode="json")}

        try:
            result = await run_summary(
                session,
                summary_type=req["summary_type"],
                date_start=req["date_start"],
                date_end=req["date_end"],
                write_notif=True,
            )
            await session.commit()
        except Exception as exc:
            logger.exception("summary_node failed: %s", exc)
            reply = "报告生成失败，请确认报告类型和日期，例如：生成今日日报、生成本周周报。"
            resp = AgentChatResponse(intent="chitchat", reply=reply, messages=[reply])
            tracer.output = {"status": "failed"}
            return {"final_response": resp.model_dump(mode="json")}

        summary = SummaryResponse(
            summary_type=result.summary_type,
            date_start=result.date_start,
            date_end=result.date_end,
            stats=_stats_to_out(result.stats),
            narrative=result.narrative,
            notification_id=result.notification_id,
        )
        reply = _summary_reply(summary)
        resp = AgentChatResponse(
            intent="generate_summary",
            summary=summary,
            reply=reply,
            messages=[reply],
        )
        final_response = resp.model_dump(mode="json")
        tracer.output = {
            "summary_type": summary.summary_type,
            "date_range": summary.stats.date_range,
            "notification_id": summary.notification_id,
        }
        return {
            "summary_obj": summary.model_dump(mode="json"),
            "reply": reply,
            "messages": [reply],
            "final_response": final_response,
        }


# ===========================================================================
# 9. Done Node
# ===========================================================================

# ===========================================================================
# 9.5 Query Node（任务查询，直接访问 DB）
# ===========================================================================

_STATUS_LABEL = {
    "pending": "待处理", "in_progress": "进行中", "completed": "已完成",
    "awaiting_review": "待审核", "cancelled": "已取消",
}
_RISK_LABEL = {"low": "低风险", "medium": "中风险", "high": "高风险", "critical": "极高风险"}
_PRIORITY_LABEL = {"low": "低", "medium": "中", "high": "高", "urgent": "紧急"}


async def query_node(state: AgentState, config: RunnableConfig) -> dict:
    """根据 query_params 执行 DB 任务查询，返回结构化结果和友好回复文本。"""
    cfg = _cfg(config)
    session = cfg.get("session")
    trace_id = state.get("trace_id")
    session_id = state.get("session_id")
    user_id = state.get("user_id")
    params = state.get("query_params") or {}

    async with NodeTracer(
        node="supervisor",
        trace_id=trace_id,
        session_id=session_id,
        tool_name="query_tasks",
        input_data={"query_params": params},
    ) as tracer:
        # ── 解析负责人 ID ──
        assignee_id: int | None = None
        assignee_label = ""
        if params.get("query_mine") and user_id:
            assignee_id = user_id
            me = await get_user_by_id(session, user_id)
            assignee_label = f"我（{me.name}）" if me else "我"
        elif params.get("query_assignee"):
            found = await find_user_by_name(session, params["query_assignee"])
            if found:
                assignee_id = found.id
                assignee_label = found.name
            else:
                assignee_label = params["query_assignee"] + "（未匹配到用户）"

        # ── 日期过滤（统一使用 naive UTC，与 DB 字段一致）──
        now_dt = _utc_now_naive()
        today_start = datetime(now_dt.year, now_dt.month, now_dt.day)
        due_before: datetime | None = None
        due_after: datetime | None = None
        date_label = ""

        if params.get("query_overdue"):
            due_before = now_dt
            date_label = "已逾期"
        elif params.get("query_due_today"):
            due_after = today_start
            due_before = today_start + timedelta(days=1)
            date_label = "今天截止"
        elif params.get("query_due_this_week"):
            week_start = today_start - timedelta(days=today_start.weekday())
            due_after = week_start
            due_before = week_start + timedelta(days=7)
            date_label = "本周截止"

        status = params.get("query_status") or None
        risk_level = params.get("query_risk") or None
        limit = params.get("query_limit") or 10

        # 逾期查询：排除已完成/已取消
        status_for_query = status
        if params.get("query_overdue") and not status:
            status_for_query = None  # list_tasks 不支持多状态，手动过滤

        tasks, total = await task_service.list_tasks(
            session,
            page=1,
            page_size=min(limit, 20),
            assignee_id=assignee_id,
            status=status_for_query,
            risk_level=risk_level,
            due_before=due_before,
            due_after=due_after,
        )

        # 逾期过滤：去掉已完成/已取消
        if params.get("query_overdue"):
            tasks = [t for t in tasks if t.status not in ("completed", "cancelled")]
            total = len(tasks)

        # ── 构建描述标签 ──
        desc_parts = []
        if assignee_label:
            desc_parts.append(f"负责人：{assignee_label}")
        if status:
            desc_parts.append(_STATUS_LABEL.get(status, status))
        if date_label:
            desc_parts.append(date_label)
        if risk_level:
            desc_parts.append(_RISK_LABEL.get(risk_level, risk_level))
        query_description = "、".join(desc_parts) + f" · 共 {total} 条（显示 {min(len(tasks), limit)} 条）"

        # ── 构建 QueryTaskItem 列表 ──
        query_items = []
        for task in tasks:
            task_due_at = _to_naive_utc(task.due_at)
            is_overdue = bool(
                task_due_at
                and task_due_at < now_dt
                and task.status not in ("completed", "cancelled")
            )
            query_items.append(
                QueryTaskItem(
                    id=task.id,
                    title=task.title,
                    status=task.status,
                    priority=task.priority,
                    risk_level=task.risk_level or "low",
                    type=task.type,
                    assignee_id=task.assignee_id,
                    due_at=task.due_at,
                    created_at=task.created_at,
                    is_overdue=is_overdue,
                )
            )

        query_result = QueryResult(
            tasks=query_items,
            total=total,
            showing=len(query_items),
            query_description=query_description,
        )

        # ── 文本回复 ──
        if not query_items:
            reply_text = f"未找到符合条件的任务（{query_description.split('·')[0].strip()}）。"
        else:
            lines = [f"查询到以下任务（{query_description}）："]
            for i, item in enumerate(query_items[:10], 1):
                due_str = item.due_at.strftime("%m/%d %H:%M") if item.due_at else "无截止"
                overdue_tag = "⚠️逾期 " if item.is_overdue else ""
                lines.append(
                    f"{i}. [{_RISK_LABEL.get(item.risk_level, item.risk_level)}] "
                    f"{item.title} — {_STATUS_LABEL.get(item.status, item.status)} "
                    f"· {overdue_tag}截止 {due_str}"
                )
            reply_text = "\n".join(lines)

        resp = AgentChatResponse(
            intent="query_task",
            reply=reply_text,
            query_result=query_result,
            messages=[],
        )
        tracer.output = {"total": total, "showing": len(query_items)}
        return {"final_response": resp.model_dump(mode="json")}


# ===========================================================================
# 10. Done Node
# ===========================================================================

async def done_node(state: AgentState, config: RunnableConfig) -> dict:
    """组装最终 AgentChatResponse，写入 final_response。"""
    # create_error 时 final_response 已在 task_node 写入，直接透传
    if state.get("create_error") and state.get("final_response"):
        return {}

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
