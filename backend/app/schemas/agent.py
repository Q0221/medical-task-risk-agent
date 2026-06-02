"""Agent 对话接口的请求/响应模型。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.task import TaskDetail


class AgentChatRequest(BaseModel):
    user_input: str = Field(..., min_length=1, max_length=2000, description="自然语言输入")
    user_id: Optional[int] = Field(
        default=None, description="发起人 user_id；缺省时使用默认管理员"
    )
    session_id: Optional[str] = Field(
        default=None, description="会话 ID，用于多轮上下文（短期记忆）"
    )


class AgentChatResponse(BaseModel):
    intent: str = Field(default="create_todo", description="Supervisor 路由结果")
    task: Optional[TaskDetail] = Field(default=None, description="创建出的任务")
    draft: Optional[dict] = Field(default=None, description="LLM 抽取的原始草稿")
    retry_count: int = Field(default=0, description="Self-Reflection 重试次数")
    messages: List[str] = Field(default_factory=list, description="过程信息 / 警告")
