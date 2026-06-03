"""RAG Agent：知识库问答 + SOP 检索 + Knowledge Gap 识别。

对外接口：
  ask_knowledge(question, task_context)  → RagAgentResult
  build_rag_query(task_draft)            → str（检索 Query）

流程：
  1. 根据任务草稿或问题构造检索 Query（LLM 可选，降本时用关键词直拼）。
  2. 调 RagClient.ask() → RagResponse。
  3. 组装 RagAgentResult，is_gap 字段透出给上层（knowledge_gap_service 使用）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.agents.llm import get_chat_model
from app.core.config import settings
from app.core.logger import get_logger
from app.rag.client import RagResponse, RetrievalHit, get_rag_client

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 结果类型
# ---------------------------------------------------------------------------

@dataclass
class RagAgentResult:
    """RAG Agent 输出，供 endpoint 和 knowledge_gap_service 使用。"""

    question: str                              # 原始问题 / 检索 Query
    answer: str                                # 生成的回答
    confidence: float                          # 0~1
    is_gap: bool                               # True → 需要建 knowledge_gap_task
    gap_reason: Optional[str]                  # gap 原因
    key_steps: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)   # SOP doc_id 列表
    hits: list[RetrievalHit] = field(default_factory=list)
    used_builtin: bool = True                  # 是否用了内置知识库

    def hits_snapshot(self) -> list[dict]:
        """转为可存储的 JSON 快照。"""
        return [
            {
                "doc_id": h.doc_id,
                "title": h.title,
                "snippet": h.snippet[:200],
                "score": h.score,
            }
            for h in self.hits
        ]


# ---------------------------------------------------------------------------
# 主接口
# ---------------------------------------------------------------------------

async def ask_knowledge(
    question: str,
    *,
    task_context: Optional[dict] = None,
) -> RagAgentResult:
    """问知识库，返回答案 + 置信度 + gap 标记。"""
    client = get_rag_client()

    # 若有任务上下文，先构造更精准的检索 Query
    query = question
    if task_context:
        try:
            query = await build_rag_query(task_context)
            logger.info("rag_agent query built: %r → %r", question[:40], query[:60])
        except Exception as exc:
            logger.warning("build_rag_query failed (%s), using original question", exc)

    rag: RagResponse = await client.ask(query, top_k=3)

    return RagAgentResult(
        question=query,
        answer=rag.answer,
        confidence=rag.confidence,
        is_gap=rag.is_gap,
        gap_reason=_extract_gap_reason(rag),
        key_steps=_extract_key_steps(rag),
        references=rag.sources,
        hits=rag.hits,
        used_builtin=rag.used_builtin,
    )


async def build_rag_query(task_context: dict) -> str:
    """从任务草稿构造 SOP 检索 Query（LLM 生成，失败时降级为规则拼接）。"""
    # 简单快路径：如果没有 LLM 或任务信息不足，用规则拼接
    task_type = task_context.get("type", "other")
    task_title = task_context.get("title", "")
    description = task_context.get("description", "")
    risk_keywords = task_context.get("risk_keywords") or []

    # 轻量规则拼接（不额外消耗 LLM token）
    parts = [task_title]
    if description:
        parts.append(description[:100])
    if risk_keywords:
        parts.append(" ".join(risk_keywords[:3]))

    rule_query = " ".join(filter(None, parts))

    # 只有在任务信息够丰富时才调 LLM 优化查询
    if len(rule_query) < 10 or not settings.LLM_API_KEY:
        return rule_query

    try:
        from app.agents.prompts import RAG_QUERY_BUILD_SYSTEM, RAG_QUERY_BUILD_USER_TMPL
        from langchain_core.messages import HumanMessage, SystemMessage

        llm = get_chat_model()
        resp = await llm.ainvoke([
            SystemMessage(content=RAG_QUERY_BUILD_SYSTEM),
            HumanMessage(content=RAG_QUERY_BUILD_USER_TMPL.format(
                task_type=task_type,
                task_title=task_title,
                task_description=description or "(无)",
                risk_level=task_context.get("risk_level", "unknown"),
                risk_keywords=", ".join(risk_keywords) if risk_keywords else "(无)",
            )),
        ])
        text = (resp.content if hasattr(resp, "content") else str(resp)).strip()
        return text if text else rule_query
    except Exception as exc:
        logger.warning("LLM query build failed: %s, using rule query", exc)
        return rule_query


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _extract_gap_reason(rag: RagResponse) -> Optional[str]:
    if not rag.is_gap:
        return None
    if not rag.hits:
        return "当前知识库中未找到相关 SOP 文档，建议补充。"
    return f"检索置信度 {rag.confidence:.0%} 低于阈值，现有文档覆盖不足。"


def _extract_key_steps(rag: RagResponse) -> list[str]:
    """从 RagResponse 提取关键步骤（如果 LLM 已解析出 key_steps 则直接用）。"""
    # 当 client 使用 LLM fallback 时，answer 中可能已有结构化字段
    # 此处做简单兜底：取 hits 的前三条 title
    if rag.hits:
        return [h.title for h in rag.hits[:3]]
    return []


__all__ = ["RagAgentResult", "ask_knowledge", "build_rag_query"]
