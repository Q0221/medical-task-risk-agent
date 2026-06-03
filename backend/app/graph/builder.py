"""LangGraph 编排图（Phase 9）。

构建并编译 StateGraph，实现以下 DAG：

  START → supervisor
            ├─[route=merge]   → merge → [route=clarify] → clarify → END
            │                         → [route=create] ↓
            ├─[route=clarify] → clarify → END
            ├─[route=create]  → task → risk → [should_rag] → rag → remind → done → END
            │                               → [!should_rag]→ remind → done → END
            └─[route=done]    → done → END

使用方式（在 agent.py 端点中）：
    from app.graph.builder import get_compiled_graph
    graph = get_compiled_graph()
    final_state = await graph.ainvoke(initial_state, config=config)
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, StateGraph

from app.agents.supervisor import route_after_merge, route_after_risk, route_after_supervisor
from app.graph.nodes import (
    clarify_node,
    done_node,
    merge_node,
    rag_node,
    remind_node,
    risk_node,
    supervisor_node,
    task_node,
)
from app.graph.state import AgentState


def build_graph() -> StateGraph:
    """构建（未编译的）StateGraph。"""
    g = StateGraph(AgentState)

    # ── 注册节点 ──────────────────────────────────────────────────────────
    g.add_node("supervisor", supervisor_node)
    g.add_node("merge", merge_node)
    g.add_node("clarify", clarify_node)
    g.add_node("task", task_node)
    g.add_node("risk", risk_node)
    g.add_node("rag", rag_node)
    g.add_node("remind", remind_node)
    g.add_node("done", done_node)

    # ── 入口 ──────────────────────────────────────────────────────────────
    g.set_entry_point("supervisor")

    # ── 条件边：supervisor → {merge | clarify | task | done} ─────────────
    g.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {
            "merge": "merge",
            "clarify": "clarify",
            "task": "task",
            "done": "done",
        },
    )

    # ── 条件边：merge → {clarify | task} ─────────────────────────────────
    g.add_conditional_edges(
        "merge",
        route_after_merge,
        {
            "clarify": "clarify",
            "task": "task",
        },
    )

    # ── 固定边：task → risk → [rag|remind] → done → END ──────────────────
    g.add_edge("task", "risk")

    g.add_conditional_edges(
        "risk",
        route_after_risk,
        {
            "rag": "rag",
            "remind": "remind",
        },
    )

    g.add_edge("rag", "remind")
    g.add_edge("remind", "done")

    # ── 终止节点 ──────────────────────────────────────────────────────────
    g.add_edge("clarify", END)
    g.add_edge("done", END)

    return g


@lru_cache(maxsize=1)
def get_compiled_graph():
    """编译图（lru_cache 确保只编译一次，类似单例）。"""
    return build_graph().compile()
