"""Agent 自然语言接口。

POST /agent/chat: 自然语言 → Task Agent 抽取 → 落库 tasks + task_events。

后续将由 LangGraph Supervisor 接管，根据 intent 路由到不同 Agent；
当前 Phase 仅实现 create_todo 单一路径。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.task_agent import extract_task
from app.api.deps import db_session
from app.core.logger import get_logger
from app.core.response import success
from app.schemas.agent import AgentChatRequest, AgentChatResponse
from app.schemas.task import TaskDetail
from app.services import task_service

router = APIRouter(prefix="/agent", tags=["agent"])
logger = get_logger(__name__)


@router.post("/chat", summary="自然语言任务入口")
async def agent_chat(
    payload: AgentChatRequest,
    request: Request,
    session: AsyncSession = Depends(db_session),
) -> dict:
    trace_id = getattr(request.state, "trace_id", None)
    logger.info(
        "agent.chat received trace_id=%s user_id=%s input=%r",
        trace_id,
        payload.user_id,
        payload.user_input,
    )

    extraction = await extract_task(payload.user_input)

    async with session.begin():
        task = await task_service.create_from_draft(
            session,
            extraction.draft,
            creator_user_id=payload.user_id,
            trace_id=trace_id,
            agent_session_id=payload.session_id,
        )

    resp = AgentChatResponse(
        intent="create_todo",
        task=TaskDetail.model_validate(task),
        draft=extraction.raw,
        retry_count=extraction.retry_count,
        messages=[f"任务已创建：id={task.id}"],
    )
    return success(resp.model_dump(mode="json"))
