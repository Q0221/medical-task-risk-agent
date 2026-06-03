"""Agent 对话接口的请求/响应模型。"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.rag import RagResultOut
from app.schemas.risk import RiskAssessment
from app.schemas.task import TaskDetail


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
    """

    intent: Literal["create_todo", "need_clarify", "chitchat", "query_task"] = Field(
        default="create_todo", description="本次处理结果类型"
    )

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
