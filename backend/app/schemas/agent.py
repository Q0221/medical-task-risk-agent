"""Agent 对话接口的请求/响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.rag import RagResultOut
from app.schemas.risk import RiskAssessment
from app.schemas.summary import SummaryResponse
from app.schemas.task import TaskDetail


# ---------------------------------------------------------------------------
# 任务查询结果
# ---------------------------------------------------------------------------

class QueryTaskItem(BaseModel):
    """查询结果中的单条任务摘要。"""
    id: int
    title: str
    status: str
    priority: str
    risk_level: str
    type: str
    assignee_id: int
    assignee_name: Optional[str] = None
    due_at: Optional[datetime] = None
    created_at: datetime
    is_overdue: bool = False


class QueryResult(BaseModel):
    """task_query 意图的结构化查询结果。"""
    tasks: List[QueryTaskItem]
    total: int
    showing: int
    query_description: str  # 如："我的待处理任务 · 今天截止 · 共 3 条"


class ThinkingStep(BaseModel):
    """单次 Agent 节点执行的思考步骤。"""
    order: int
    node: str
    node_label: str
    status: str
    duration_ms: int
    summary: str
    input_data: Optional[dict] = None
    output_data: Optional[dict] = None
    tool_name: Optional[str] = None
    error_message: Optional[str] = None


class AgentChatRequest(BaseModel):
    user_input: str = Field(..., min_length=1, max_length=2000, description="自然语言输入")
    user_id: Optional[int] = Field(
        default=None, description="发起人 user_id；缺省时使用默认管理员"
    )
    session_id: Optional[str] = Field(
        default=None, description="会话 ID，用于多轮补全上下文"
    )


class AgentChatResponse(BaseModel):
    """统一响应体，intent 决定哪些字段有值。

    intent 值说明：
    - create_todo   : 任务已创建，task / draft / risk_assessment 有值
    - need_clarify  : 字段缺失，question / session_id 有值，等待用户补充
    - chitchat      : 闲聊/问候，reply 有值，不建任务
    - query_task    : 用户想查任务，reply 中有引导说明
    - generate_summary : 已生成日报/周报，summary / reply 有值
    - create_error  : 任务创建失败但可恢复，draft/candidates 保留供前端提示
    """

    intent: Literal[
        "create_todo", "need_clarify", "chitchat", "query_task",
        "generate_summary", "create_error",
    ] = Field(default="create_todo", description="本次处理结果类型")

    # ── 建任务成功 ──
    task: Optional[TaskDetail] = Field(default=None, description="创建出的任务")
    draft: Optional[dict] = Field(default=None, description="LLM 抽取的原始草稿")
    retry_count: int = Field(default=0, description="Self-Reflection 重试次数")
    risk_assessment: Optional[RiskAssessment] = Field(
        default=None, description="Risk Agent 评估结果"
    )
    rag_result: Optional[RagResultOut] = Field(
        default=None, description="RAG Agent SOP 检索结果（高风险任务自动触发）"
    )
    summary: Optional[SummaryResponse] = Field(
        default=None, description="日报/周报生成结果（generate_summary 时有值）"
    )
    query_result: Optional[QueryResult] = Field(
        default=None, description="query_task 时的结构化查询结果"
    )

    # ── 需要追问 ──
    question: Optional[str] = Field(
        default=None, description="需要向用户追问的问题（need_clarify 时有值）"
    )
    session_id: Optional[str] = Field(
        default=None, description="多轮会话 ID，用户下一条消息需携带"
    )

    # ── 闲聊/查询 ──
    reply: Optional[str] = Field(
        default=None, description="对闲聊或查询请求的友好回复"
    )

    messages: List[str] = Field(default_factory=list, description="过程信息 / 警告")

    # ── 思考过程 ──
    trace_id: Optional[str] = Field(
        default=None, description="本次请求链路 ID，可用于查询思考过程"
    )
    thinking_steps: List[ThinkingStep] = Field(
        default_factory=list, description="Agent 节点执行步骤（思考过程）"
    )

    # ── 可恢复错误 ──
    is_recoverable: bool = Field(
        default=False, description="创建失败但草稿保留，前端可展示候选项让用户修正后重提"
    )
    error_message: Optional[str] = Field(
        default=None, description="create_error 时的错误说明"
    )
    candidates: Optional[Dict[str, List[dict]]] = Field(
        default=None,
        description=(
            "create_error 时返回的候选项，结构示例："
            '{"assignee": [{"id":1,"name":"张三","extra":{}}], "hospital": [...]}'
        ),
    )


# ---------------------------------------------------------------------------
# 草稿确认请求（跳过 LLM，直接落库）
# ---------------------------------------------------------------------------

class DraftConfirmRequest(BaseModel):
    """POST /agent/confirm-draft 请求体：直接从已解析草稿创建任务，不再走 LLM。

    assignee_id / hospital_id / product_id 为可选预解析 ID，有值时跳过名称查找。
    """

    session_id: Optional[str] = None

    title: str = Field(..., min_length=1, max_length=200)
    type: str = "other"
    priority: str = "medium"
    description: Optional[str] = None

    assignee_name: Optional[str] = None
    assignee_id: Optional[int] = None   # 优先：跳过名称查找
    hospital_name: Optional[str] = None
    hospital_id: Optional[int] = None   # 优先
    product_name: Optional[str] = None
    product_id: Optional[int] = None    # 优先

    business_object_type: str = "none"
    business_object_id: Optional[str] = None

    due_at: Optional[datetime] = None
    remind_at: Optional[datetime] = None
    risk_keywords: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 候选项（用于名称解析失败时的前端确认）
# ---------------------------------------------------------------------------

class CandidateItem(BaseModel):
    id: int
    name: str
    extra: Optional[dict] = None  # employee_no / department / city 等


class CandidatesResponse(BaseModel):
    entity_type: str  # user | hospital | product
    query: str
    items: List[CandidateItem]


# ---------------------------------------------------------------------------
# 会话历史消息
# ---------------------------------------------------------------------------

class HistoryMessage(BaseModel):
    role: str          # "user" | "agent"
    text: str
    time: str
    intent: Optional[str] = None
    task_id: Optional[int] = None
    is_error: bool = False


class SessionHistoryResponse(BaseModel):
    session_id: str
    messages: List[HistoryMessage]
