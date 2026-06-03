"""RAG 客户端：支持外部 HTTP RAG 服务（配置 RAG_BASE_URL 时生效）或内置 LLM 兜底。

外部 RAG 协议（POST {RAG_BASE_URL}/retrieve）：
  Request:  {"query": str, "top_k": int}
  Response: {"hits": [{"doc_id": str, "title": str, "snippet": str, "score": float}]}

外部 RAG 协议（POST {RAG_BASE_URL}/ask）：
  Request:  {"question": str, "top_k": int}
  Response: {"answer": str, "confidence": float,
             "hits": [...], "sources": [str]}

无外部服务时回落到：关键词粗筛内置 SOP → LLM 生成答案 + 置信度。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.core.config import settings
from app.core.logger import get_logger
from app.rag.sop_data import BUILTIN_SOPS, retrieve_by_keywords

logger = get_logger(__name__)

# 置信度低于此阈值触发 Knowledge Gap
CONFIDENCE_THRESHOLD = 0.55


@dataclass
class RetrievalHit:
    doc_id: str
    title: str
    snippet: str
    score: float


@dataclass
class RagResponse:
    answer: str
    confidence: float
    hits: list[RetrievalHit] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    is_gap: bool = False          # confidence < CONFIDENCE_THRESHOLD
    used_builtin: bool = False    # 是否使用了内置知识库


class RagClient:
    """RAG 客户端，优先调用外部服务，回落内置知识库 + LLM。"""

    def __init__(self) -> None:
        self._base_url = (settings.RAG_BASE_URL or "").rstrip("/")
        self._api_key = settings.RAG_API_KEY or ""

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    async def ask(self, question: str, *, top_k: int = 3) -> RagResponse:
        """知识问答：先检索相关 SOP，再生成回答 + 置信度。"""
        if self._base_url:
            try:
                return await self._ask_remote(question, top_k=top_k)
            except Exception as exc:
                logger.warning("remote RAG ask failed (%s), falling back to builtin", exc)

        return await self._ask_builtin(question, top_k=top_k)

    async def retrieve(self, query: str, *, top_k: int = 3) -> list[RetrievalHit]:
        """仅检索，不生成答案。"""
        if self._base_url:
            try:
                return await self._retrieve_remote(query, top_k=top_k)
            except Exception as exc:
                logger.warning("remote RAG retrieve failed (%s), falling back to builtin", exc)

        return self._retrieve_builtin(query, top_k=top_k)

    # ------------------------------------------------------------------
    # 外部 HTTP RAG 服务
    # ------------------------------------------------------------------

    async def _ask_remote(self, question: str, top_k: int) -> RagResponse:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self._base_url}/ask",
                headers=headers,
                json={"question": question, "top_k": top_k},
            )
            resp.raise_for_status()
            data = resp.json()

        hits = [
            RetrievalHit(
                doc_id=h.get("doc_id", ""),
                title=h.get("title", ""),
                snippet=h.get("snippet", ""),
                score=float(h.get("score", 0)),
            )
            for h in data.get("hits", [])
        ]
        confidence = float(data.get("confidence", 0.5))
        return RagResponse(
            answer=data.get("answer", ""),
            confidence=confidence,
            hits=hits,
            sources=[h.doc_id for h in hits],
            is_gap=confidence < CONFIDENCE_THRESHOLD,
            used_builtin=False,
        )

    async def _retrieve_remote(self, query: str, top_k: int) -> list[RetrievalHit]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{self._base_url}/retrieve",
                headers=headers,
                json={"query": query, "top_k": top_k},
            )
            resp.raise_for_status()
            data = resp.json()

        return [
            RetrievalHit(
                doc_id=h.get("doc_id", ""),
                title=h.get("title", ""),
                snippet=h.get("snippet", ""),
                score=float(h.get("score", 0)),
            )
            for h in data.get("hits", [])
        ]

    # ------------------------------------------------------------------
    # 内置知识库 + LLM
    # ------------------------------------------------------------------

    async def _ask_builtin(self, question: str, top_k: int) -> RagResponse:
        """关键词粗筛 SOP → LLM 生成结构化回答。"""
        scored = retrieve_by_keywords(question, top_k=top_k)

        hits = [
            RetrievalHit(
                doc_id=doc.doc_id,
                title=doc.title,
                snippet=doc.content[:300].replace("\n", " "),
                score=score,
            )
            for doc, score in scored
        ]

        if not hits:
            # 完全无匹配 → 直接声明 gap
            return RagResponse(
                answer="当前知识库中未找到与该问题相关的 SOP 文档，建议补充相关操作规范。",
                confidence=0.0,
                hits=[],
                sources=[],
                is_gap=True,
                used_builtin=True,
            )

        # 拼接检索到的 SOP 内容作为 context
        context_parts = []
        for doc, score in scored:
            context_parts.append(f"【{doc.title}（{doc.doc_id}，匹配度 {score:.0%}）】\n{doc.content.strip()}")
        context = "\n\n---\n\n".join(context_parts)

        # 调 LLM 生成结构化答案
        try:
            from app.agents.prompts import RAG_QA_SYSTEM, RAG_QA_USER_TMPL
            from app.agents.llm import get_chat_model
            from langchain_core.messages import HumanMessage, SystemMessage

            llm = get_chat_model()
            response = await llm.ainvoke([
                SystemMessage(content=RAG_QA_SYSTEM),
                HumanMessage(content=RAG_QA_USER_TMPL.format(
                    context=context,
                    question=question,
                )),
            ])
            raw = response.content if hasattr(response, "content") else str(response)
            parsed = _extract_json(raw)
        except Exception as exc:
            logger.warning("LLM RAG answer generation failed: %s", exc)
            # 回落：直接截取第一条 SOP 摘要作为答案
            best_doc, best_score = scored[0]
            return RagResponse(
                answer=f"参考 {best_doc.title}：{best_doc.content[:400]}",
                confidence=best_score * 0.8,
                hits=hits,
                sources=[doc.doc_id for doc, _ in scored],
                is_gap=best_score < CONFIDENCE_THRESHOLD,
                used_builtin=True,
            )

        confidence = float(parsed.get("confidence", max(s for _, s in scored)))
        return RagResponse(
            answer=parsed.get("answer", ""),
            confidence=confidence,
            hits=hits,
            sources=[doc.doc_id for doc, _ in scored],
            is_gap=confidence < CONFIDENCE_THRESHOLD,
            used_builtin=True,
        )

    def _retrieve_builtin(self, query: str, top_k: int) -> list[RetrievalHit]:
        scored = retrieve_by_keywords(query, top_k=top_k)
        return [
            RetrievalHit(
                doc_id=doc.doc_id,
                title=doc.title,
                snippet=doc.content[:300].replace("\n", " "),
                score=score,
            )
            for doc, score in scored
        ]


# ------------------------------------------------------------------
# 模块级单例
# ------------------------------------------------------------------

def get_rag_client() -> RagClient:
    return RagClient()


# ------------------------------------------------------------------
# 工具
# ------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    import re
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        text = text[brace_start:brace_end + 1]
    try:
        return json.loads(text)
    except Exception:
        return {}


__all__ = ["RagClient", "RagResponse", "RetrievalHit", "get_rag_client", "CONFIDENCE_THRESHOLD"]
