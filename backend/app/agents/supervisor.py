"""Supervisor 路由节点（Phase 9）。

提供给 graph/builder.py 使用的条件路由函数：
  route_after_supervisor(state) → 下一节点名
  route_after_merge(state)      → 下一节点名
  route_after_risk(state)       → 下一节点名
"""

from __future__ import annotations

from app.graph.state import AgentState


def route_after_supervisor(state: AgentState) -> str:
    """Supervisor 后的路由：根据 state["route"] 决定下一节点。"""
    route = state.get("route", "done")
    if route == "merge":
        return "merge"
    if route == "clarify":
        return "clarify"
    if route == "create":
        return "task"
    if route == "summary":
        return "summary"
    if route == "query":
        return "query"
    return "done"


def route_after_merge(state: AgentState) -> str:
    """Merge 后的路由：字段仍缺 → clarify；字段完整 → task。"""
    route = state.get("route", "clarify")
    return "clarify" if route == "clarify" else "task"


def route_after_risk(state: AgentState) -> str:
    """Risk 后的路由：高风险或特定类型 → rag；否则 → remind。"""
    return "rag" if state.get("should_rag") else "remind"
