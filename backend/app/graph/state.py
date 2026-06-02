"""LangGraph State 定义（占位）。

后续将定义 AgentState（TypedDict），承载：
- user_input、user_id、role、trace_id
- intent、task_draft、risk_level、risk_reason
- rag_query、rag_hits、rag_confidence
- review_status、retry_count、tool_calls、messages
"""

from typing import TypedDict


class AgentState(TypedDict, total=False):
    user_input: str
    user_id: str
    trace_id: str
