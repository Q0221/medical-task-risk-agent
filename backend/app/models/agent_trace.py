"""Agent 执行链路本地审计。

LangSmith 是 SaaS，可能受网络/合规限制；此表用于本地常驻审计，
记录 Supervisor 路由、各节点 IO、工具调用、耗时、错误、重试次数。
"""

from typing import Optional

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel
from app.models.enums import AgentNode, AgentTraceStatus


class AgentTrace(BaseModel):
    __tablename__ = "agent_traces"
    __table_args__ = (
        Index("ix_agent_traces_trace_node", "trace_id", "node"),
    )

    trace_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="一次请求级链路 ID"
    )
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("agent_traces.id", ondelete="SET NULL"),
        nullable=True,
        comment="父节点 trace 主键，可形成树",
    )
    session_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True, comment="会话 ID"
    )
    node: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=AgentNode.SUPERVISOR.value,
        index=True,
        comment="LangGraph 节点名",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=AgentTraceStatus.OK.value,
        index=True,
    )
    input_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    output_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    tool_name: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="若该节点是 Tool Call，记录工具名"
    )
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
