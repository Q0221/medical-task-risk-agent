"""RAG 知识问答相关 Pydantic 模型。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class KnowledgeQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000, description="知识问题或 SOP 查询")
    task_id: Optional[int] = Field(
        default=None, ge=1, description="关联的任务 ID（可选，用于构造更精准的检索 Query）"
    )
    user_id: Optional[int] = Field(
        default=None, ge=1, description="发起人 user_id，知识空缺任务分派时使用"
    )


class RetrievalHitOut(BaseModel):
    doc_id: str
    title: str
    snippet: str
    score: float


class RagResultOut(BaseModel):
    """RAG 知识问答响应。"""

    question: str = Field(..., description="实际检索 Query")
    answer: str = Field(..., description="基于 SOP 生成的回答")
    confidence: float = Field(..., description="答案置信度 0~1")
    is_gap: bool = Field(..., description="True 表示置信度低，已创建知识空缺任务")
    gap_reason: Optional[str] = Field(default=None, description="知识空缺原因")
    gap_task_id: Optional[int] = Field(default=None, description="自动创建的 knowledge_gap_task id")
    key_steps: List[str] = Field(default_factory=list, description="关键执行步骤（精简版）")
    references: List[str] = Field(default_factory=list, description="引用的 SOP 文档 ID")
    hits: List[RetrievalHitOut] = Field(default_factory=list, description="检索命中详情")
    used_builtin: bool = Field(default=True, description="是否使用了内置知识库")
