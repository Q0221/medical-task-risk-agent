"""将 AgentTrace 记录格式化为前端可展示的思考步骤。"""

from __future__ import annotations

from typing import Any, Optional

from app.models.agent_trace import AgentTrace
from app.schemas.agent import ThinkingStep

_NODE_LABELS: dict[str, str] = {
    "supervisor": "意图识别与路由",
    "merge": "多轮信息合并",
    "clarify": "追问补全",
    "task_agent": "任务创建",
    "risk_agent": "风险评估",
    "rag_agent": "知识库检索",
    "summary_agent": "报告生成",
    "notify_agent": "通知调度",
    "human_review": "人工审核",
    "tool_call": "工具调用",
}

_ROUTE_LABELS: dict[str, str] = {
    "merge": "进入多轮补全",
    "clarify": "发起追问",
    "create": "进入任务创建",
    "summary": "进入报告生成",
    "query": "进入任务查询",
    "done": "直接回复用户",
}

_STATUS_LABELS: dict[str, str] = {
    "pending": "待处理",
    "in_progress": "进行中",
    "completed": "已完成",
    "awaiting_review": "待审核",
    "cancelled": "已取消",
}


def _safe_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _summarize_supervisor(input_data: dict, output_data: dict, tool_name: Optional[str]) -> str:
    if tool_name == "query_tasks":
        total = output_data.get("total")
        showing = output_data.get("showing")
        if total is not None:
            return f"按条件查询任务，共 {total} 条，展示 {showing or 0} 条"
        return "执行任务查询"

    route = output_data.get("route")
    if route:
        route_text = _ROUTE_LABELS.get(route, route)
        if route == "query" and output_data.get("query_params"):
            params = output_data["query_params"]
            parts = []
            if params.get("query_assignee"):
                parts.append(f"负责人={params['query_assignee']}")
            if params.get("query_status"):
                parts.append(f"状态={_STATUS_LABELS.get(params['query_status'], params['query_status'])}")
            if params.get("query_mine"):
                parts.append("我的任务")
            suffix = f"（{', '.join(parts)}）" if parts else ""
            return f"{route_text}{suffix}"
        if route == "clarify" and output_data.get("pending_field"):
            return f"{route_text}，待补充字段：{output_data['pending_field']}"
        if route == "summary" and output_data.get("summary_type"):
            period = "周报" if output_data["summary_type"] == "weekly" else "日报"
            return f"{route_text}，生成{period}"
        if output_data.get("intent"):
            return f"{route_text}，识别意图：{output_data['intent']}"
        return route_text

    user_input = input_data.get("user_input")
    if user_input:
        preview = str(user_input)[:40]
        return f"分析用户输入：{preview}{'…' if len(str(user_input)) > 40 else ''}"
    return "分析用户意图并决定下一步"


def _summarize_merge(output_data: dict) -> str:
    route = output_data.get("route")
    if route == "create":
        return "用户补充信息已合并，字段齐全，准备创建任务"
    if route == "clarify":
        field = output_data.get("pending_field") or "必要字段"
        return f"合并后仍缺少 {field}，继续追问"
    return "合并用户补充信息到任务草稿"


def _summarize_clarify(output_data: dict) -> str:
    field = output_data.get("pending_field") or "必要信息"
    return f"保存待补全草稿，等待用户补充：{field}"


def _summarize_task_agent(output_data: dict) -> str:
    if output_data.get("task_id"):
        title = output_data.get("title") or ""
        return f"任务已写入数据库 #{output_data['task_id']} {title}".strip()
    if output_data.get("error"):
        return f"任务创建失败：{output_data['error']}"
    return "执行任务落库"


def _summarize_risk_agent(output_data: dict) -> str:
    level = output_data.get("level") or output_data.get("risk_level")
    requires_review = output_data.get("requires_review")
    if level:
        review_text = "，需人工审核" if requires_review else ""
        return f"评估风险等级：{level}{review_text}"
    return "完成任务风险识别"


def _summarize_rag_agent(output_data: dict) -> str:
    if output_data.get("is_gap"):
        return "知识库未命中，已记录知识缺口"
    hit_count = output_data.get("hit_count")
    if hit_count is not None:
        return f"检索到 {hit_count} 条相关知识片段"
    if output_data.get("answer"):
        return "已匹配 SOP / 知识库建议"
    return "执行知识库检索"


def _summarize_summary_agent(output_data: dict) -> str:
    if output_data.get("notification_id"):
        period = "周报" if output_data.get("summary_type") == "weekly" else "日报"
        return f"{period}已生成，通知记录 #{output_data['notification_id']}"
    if output_data.get("status") == "failed":
        return "报告生成失败"
    return "生成统计报告"


def _build_summary(trace: AgentTrace) -> str:
    input_data = _safe_dict(trace.input_data)
    output_data = _safe_dict(trace.output_data)
    node = trace.node

    if node == "supervisor":
        return _summarize_supervisor(input_data, output_data, trace.tool_name)
    if node == "merge":
        return _summarize_merge(output_data)
    if node == "clarify":
        return _summarize_clarify(output_data)
    if node == "task_agent":
        return _summarize_task_agent(output_data)
    if node == "risk_agent":
        return _summarize_risk_agent(output_data)
    if node == "rag_agent":
        return _summarize_rag_agent(output_data)
    if node == "summary_agent":
        return _summarize_summary_agent(output_data)
    if trace.error_message:
        return trace.error_message
    return f"执行节点 {node}"


def build_thinking_steps(traces: list[AgentTrace]) -> list[ThinkingStep]:
    """把链路追踪记录转成按时间排序的思考步骤。"""
    steps: list[ThinkingStep] = []
    for index, trace in enumerate(traces, start=1):
        node_label = _NODE_LABELS.get(trace.node, trace.node)
        if trace.tool_name:
            node_label = f"{node_label} · {trace.tool_name}"

        steps.append(
            ThinkingStep(
                order=index,
                node=trace.node,
                node_label=node_label,
                status=trace.status,
                duration_ms=trace.duration_ms,
                summary=_build_summary(trace),
                input_data=trace.input_data,
                output_data=trace.output_data,
                tool_name=trace.tool_name,
                error_message=trace.error_message,
            )
        )
    return steps


__all__ = ["build_thinking_steps"]
