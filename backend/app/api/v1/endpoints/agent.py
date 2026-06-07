"""Agent 自然语言对话入口（Phase 9 — LangGraph 编排）。

POST /agent/chat 通过 LangGraph StateGraph 编排以下节点：
  supervisor → [merge|clarify|task] → risk → [rag] → remind → done

每个节点均写入 agent_traces 表（trace_service.NodeTracer）。
多轮会话状态通过 Redis（session_service）跨请求持久化。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from langchain_core.runnables import RunnableConfig
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, redis_client
from app.core.exceptions import BizException
from app.core.logger import get_logger
from app.core.response import success
from app.graph.builder import get_compiled_graph
from app.schemas.agent import AgentChatRequest, AgentChatResponse

router = APIRouter(prefix="/agent", tags=["agent"])
logger = get_logger(__name__)


@router.post("/chat", summary="自然语言任务入口（LangGraph 编排，含意图识别 + 多轮追问）")
async def agent_chat(
    payload: AgentChatRequest,
    request: Request,
    session: AsyncSession = Depends(db_session),
    redis: Redis = Depends(redis_client),
) -> dict:
    """通过 LangGraph StateGraph 编排全流程：

    - **首轮建任务**：意图识别 → 若字段完整则建任务→风险评估→RAG→提醒注册
    - **字段缺失**：返回 need_clarify + session_id，等待下一轮补充
    - **多轮续接**：session_id 对应 Redis pending → merge_node 合并后继续
    - **闲聊/查询**：直接返回 chitchat/query_task 响应，不建任务
    - **全流程 agent_traces 持久化**：每节点写入 agent_traces 表
    """
    trace_id = getattr(request.state, "trace_id", None)
    logger.info(
        "agent.chat trace_id=%s session_id=%s user_id=%s input=%r",
        trace_id,
        payload.session_id,
        payload.user_id,
        payload.user_input,
    )

    # 初始化 AgentState
    initial_state = {
        "user_input": payload.user_input,
        "user_id": payload.user_id,
        "session_id": payload.session_id,
        "trace_id": trace_id,
        "messages": [],
        "retry_count": 0,
        "should_rag": False,
        "risk_requires_review": False,
        "risk_llm_failed": False,
        "reminder_scheduled": False,
    }

    # 将 session / redis 通过 RunnableConfig 传入各节点
    graph_config = RunnableConfig(
        configurable={
            "session": session,
            "redis": redis,
        }
    )

    # 编排执行
    compiled_graph = get_compiled_graph()
    try:
        final_state = await compiled_graph.ainvoke(initial_state, config=graph_config)
    except BizException as exc:
        logger.warning("graph.ainvoke business error: code=%s message=%s", exc.code, exc.message)
        reply = _agent_error_reply(exc)
        resp = AgentChatResponse(
            intent="chitchat",
            reply=reply,
            messages=[reply],
        )
        return success(resp.model_dump(mode="json"))
    except Exception as exc:
        logger.exception("graph.ainvoke failed: %s", exc)
        # 降级：返回友好错误，不暴露内部异常细节。
        resp = AgentChatResponse(
            intent="chitchat",
            reply=_agent_error_reply(),
            messages=[],
        )
        return success(resp.model_dump(mode="json"))

    # final_response 由 clarify_node 或 done_node 写入
    final_response = final_state.get("final_response")
    if final_response is None:
        logger.error("graph returned no final_response, state=%s", final_state)
        resp = AgentChatResponse(intent="chitchat", reply="处理完成，但无法生成响应", messages=[])
        return success(resp.model_dump(mode="json"))

    return success(final_response)


def _agent_error_reply(exc: BizException | None = None) -> str:
    if exc and exc.code in {4001, 4041, 4042, 4044, 4090}:
        return exc.message
    return "我没能完成解析，请重新描述任务，并明确具体任务、负责人和时间。"
