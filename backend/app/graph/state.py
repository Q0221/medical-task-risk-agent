"""LangGraph AgentState（Phase 9）。

承载整次 /agent/chat 请求在各节点间流转的所有状态。
所有字段 total=False（Optional），每个节点只更新自己负责的字段。
"""

from __future__ import annotations

from typing import Any, Optional
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    # ── 请求上下文（入口写入，只读）───────────────────────────────────────────
    user_input: str
    user_id: Optional[int]
    session_id: Optional[str]       # 前端传入的多轮 session_id（可为 None）
    trace_id: Optional[str]         # HTTP 请求级链路 ID（TraceIdMiddleware 注入）

    # ── Supervisor 路由决策 ─────────────────────────────────────────────────
    route: str                      # "clarify" | "merge" | "create" | "done"
    intent: str                     # create_task | chitchat | query_task | unclear

    # ── Task Agent 输出（extract / merge） ──────────────────────────────────
    draft_raw: Optional[dict]       # LLM 原始 JSON 输出（用于多轮追问时的 merge）
    task_draft: Optional[dict]      # 已验证的 TaskDraft 序列化字典
    pending_field: Optional[str]    # 缺失的业务必填字段名
    pending_question: Optional[str] # 针对该字段的追问文本
    reply: Optional[str]            # chitchat / query 场景的直接回复

    # ── Task Service 输出 ───────────────────────────────────────────────────
    task_id: Optional[int]
    task_obj: Optional[dict]        # 序列化 TaskDetail（供 done_node 组装响应）

    # ── Risk Service 输出 ───────────────────────────────────────────────────
    risk_level: Optional[str]
    risk_requires_review: bool
    risk_llm_failed: bool
    risk_assessment: Optional[Any]  # RiskAssessment 对象（done_node 用）

    # ── RAG Agent 输出 ──────────────────────────────────────────────────────
    should_rag: bool
    rag_result: Optional[Any]       # RagAgentResult
    gap_task_id: Optional[int]      # 创建的 KnowledgeGap 任务 ID

    # ── Remind ─────────────────────────────────────────────────────────────
    reminder_scheduled: bool

    # ── 最终响应组装 ────────────────────────────────────────────────────────
    messages: list[str]             # 面向用户的提示消息列表
    final_response: Optional[dict]  # AgentChatResponse.model_dump(mode="json")

    # ── 重试计数（Task Agent 自我反思） ────────────────────────────────────
    retry_count: int

    # ── Trace 上下文（由 trace_service 填充） ─────────────────────────────
    trace_root_id: Optional[int]    # 本次请求的根 AgentTrace.id
