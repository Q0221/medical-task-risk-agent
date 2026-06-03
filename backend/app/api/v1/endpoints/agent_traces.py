"""Agent Trace 查询接口（Phase 9）。

GET /agent/traces?trace_id=...      → 单次请求全链路
GET /agent/traces?session_id=...    → 某会话全链路
GET /agent/traces?node=...&page=... → 按节点类型分页
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.core.response import success
from app.models.agent_trace import AgentTrace

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentTraceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trace_id: str
    parent_id: Optional[int]
    session_id: Optional[str]
    node: str
    status: str
    input_data: Optional[dict]
    output_data: Optional[dict]
    tool_name: Optional[str]
    duration_ms: int
    retry_count: int
    error_message: Optional[str]
    created_at: Optional[object]  # datetime


@router.get("/traces", summary="查询 Agent 执行链路（Phase 9）")
async def list_traces(
    trace_id: Optional[str] = Query(default=None, description="按请求级 trace_id 过滤"),
    session_id: Optional[str] = Query(default=None, description="按会话 session_id 过滤"),
    node: Optional[str] = Query(default=None, description="按节点名过滤：supervisor / task_agent / risk_agent 等"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(db_session),
) -> dict:
    """查询 agent_traces 表，支持 trace_id / session_id / node 过滤，按 id 升序。

    通常用法：
    - `?trace_id=xxx` 查看一次 /agent/chat 请求走过的所有节点及耗时
    - `?session_id=yyy` 查看多轮对话全过程
    - `?node=risk_agent` 查看最近风险评估节点执行情况
    """
    async with session.begin():
        base = select(AgentTrace).where(AgentTrace.deleted_at.is_(None))
        count_q = (
            select(func.count())
            .select_from(AgentTrace)
            .where(AgentTrace.deleted_at.is_(None))
        )

        if trace_id:
            base = base.where(AgentTrace.trace_id == trace_id)
            count_q = count_q.where(AgentTrace.trace_id == trace_id)
        if session_id:
            base = base.where(AgentTrace.session_id == session_id)
            count_q = count_q.where(AgentTrace.session_id == session_id)
        if node:
            base = base.where(AgentTrace.node == node)
            count_q = count_q.where(AgentTrace.node == node)

        total = (await session.execute(count_q)).scalar_one()
        offset = (page - 1) * page_size
        items = (
            await session.execute(
                base.order_by(AgentTrace.id).offset(offset).limit(page_size)
            )
        ).scalars().all()

    return success({
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [AgentTraceOut.model_validate(t).model_dump(mode="json") for t in items],
    })
