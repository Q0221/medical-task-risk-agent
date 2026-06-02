"""Supervisor 节点（占位）。

职责：
- 根据用户意图、字段完整性、风险等级与业务场景，动态路由到
  Task / Risk / RAG / Notify / Summary 等专家 Agent。
- 维护多轮会话状态（agent_session_context）与 trace_id。
"""


async def route(state: dict) -> dict:
    # TODO: 接入 LangGraph 后实现真正的 Supervisor 路由逻辑。
    raise NotImplementedError
