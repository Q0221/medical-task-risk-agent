"""Agent Trace 持久化服务（Phase 9）。

使用独立 DB Session（与主请求事务隔离），确保即使主流程失败也能写入链路记录。

主要接口：
  write_trace(node, status, input_data, output_data, ...) → AgentTrace.id
  get_traces(trace_id)    → list[AgentTrace]
  get_session_traces(session_id) → list[AgentTrace]
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import AsyncSessionLocal
from app.core.logger import get_logger
from app.models.agent_trace import AgentTrace
from app.models.enums import AgentTraceStatus

logger = get_logger(__name__)


async def write_trace(
    *,
    node: str,
    status: str = AgentTraceStatus.OK.value,
    trace_id: Optional[str] = None,
    session_id: Optional[str] = None,
    parent_id: Optional[int] = None,
    input_data: Optional[dict] = None,
    output_data: Optional[dict] = None,
    tool_name: Optional[str] = None,
    duration_ms: int = 0,
    retry_count: int = 0,
    error_message: Optional[str] = None,
) -> Optional[int]:
    """写入一条 AgentTrace 记录，使用独立 session 保证不受主流程事务影响。

    返回新记录的 id，写入失败时返回 None（非致命错误，仅打印日志）。
    """
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                trace = AgentTrace(
                    trace_id=trace_id or "unknown",
                    parent_id=parent_id,
                    session_id=session_id,
                    node=node,
                    status=status,
                    input_data=input_data,
                    output_data=output_data,
                    tool_name=tool_name,
                    duration_ms=duration_ms,
                    retry_count=retry_count,
                    error_message=error_message,
                )
                session.add(trace)
                await session.flush()
                trace_id_val = trace.id
        return trace_id_val
    except Exception as exc:
        logger.warning("trace write failed (non-fatal): node=%s error=%s", node, exc)
        return None


class NodeTracer:
    """上下文管理器：包裹一个节点的执行，自动计时并写入 AgentTrace。

    用法：
        async with NodeTracer(node="risk_agent", trace_id=..., session_id=...) as t:
            result = await do_work()
            t.output = {"level": result.level}
    """

    def __init__(
        self,
        *,
        node: str,
        trace_id: Optional[str] = None,
        session_id: Optional[str] = None,
        parent_id: Optional[int] = None,
        input_data: Optional[dict] = None,
        tool_name: Optional[str] = None,
        retry_count: int = 0,
    ) -> None:
        self.node = node
        self.trace_id = trace_id
        self.session_id = session_id
        self.parent_id = parent_id
        self.input_data = input_data
        self.tool_name = tool_name
        self.retry_count = retry_count
        self.output: Optional[dict] = None
        self._start: float = 0
        self.record_id: Optional[int] = None

    async def __aenter__(self) -> "NodeTracer":
        self._start = time.monotonic()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, _tb: Any) -> bool:
        duration_ms = int((time.monotonic() - self._start) * 1000)
        status = AgentTraceStatus.ERROR.value if exc_type else AgentTraceStatus.OK.value
        error_msg = str(exc_val) if exc_val else None

        self.record_id = await write_trace(
            node=self.node,
            status=status,
            trace_id=self.trace_id,
            session_id=self.session_id,
            parent_id=self.parent_id,
            input_data=self.input_data,
            output_data=self.output,
            tool_name=self.tool_name,
            duration_ms=duration_ms,
            retry_count=self.retry_count,
            error_message=error_msg,
        )
        return False  # 不吞异常


async def get_traces(trace_id: str) -> list[AgentTrace]:
    """查询同一 trace_id 下的全部 AgentTrace，按 id 升序。"""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            rows = (
                await session.execute(
                    select(AgentTrace)
                    .where(AgentTrace.trace_id == trace_id, AgentTrace.deleted_at.is_(None))
                    .order_by(AgentTrace.id)
                )
            ).scalars().all()
    return list(rows)


async def get_session_traces(session_id: str) -> list[AgentTrace]:
    """查询同一 session_id 下的全部 AgentTrace，按 id 升序。"""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            rows = (
                await session.execute(
                    select(AgentTrace)
                    .where(
                        AgentTrace.session_id == session_id,
                        AgentTrace.deleted_at.is_(None),
                    )
                    .order_by(AgentTrace.id)
                )
            ).scalars().all()
    return list(rows)


__all__ = ["write_trace", "NodeTracer", "get_traces", "get_session_traces"]
