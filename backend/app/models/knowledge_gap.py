"""知识空缺任务。

当 RAG 检索置信度低 / 无有效 SOP / 员工反馈答案不完整时，
由 Agent 自动生成一条「知识库补充任务」，分派给医学支持或产品运营。
"""

from typing import Optional

from sqlalchemy import JSON, BigInteger, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel
from app.models.enums import KnowledgeGapStatus


class KnowledgeGapTask(BaseModel):
    __tablename__ = "knowledge_gap_tasks"

    source_task_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="触发该知识空缺的原始任务",
    )
    original_question: Mapped[str] = mapped_column(Text, nullable=False, comment="原始问题")
    retrieval_query: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="实际检索 Query"
    )
    confidence: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="RAG 检索置信度 0~1"
    )
    rag_hits_snapshot: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="检索结果快照（doc_id/score/snippet）"
    )

    assignee_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="知识补充任务责任人",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=KnowledgeGapStatus.OPEN.value,
        index=True,
    )
    resolution_note: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="解决说明（SOP 链接 / 文档地址）"
    )
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
