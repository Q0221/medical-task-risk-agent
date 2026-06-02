"""LLM 客户端：阿里云百炼 qwen-plus（通过 OpenAI 兼容协议）。

百炼提供 OpenAI 兼容端点，直接复用 langchain_openai.ChatOpenAI：
    base_url = https://dashscope.aliyuncs.com/compatible-mode/v1
    model    = qwen-plus（或 qwen-max / qwen-turbo）

支持注入 mock LLM，用于单元测试。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.exceptions import BizException


_override: Optional[BaseChatModel] = None


def set_chat_model(model: Optional[BaseChatModel]) -> None:
    """测试期注入 mock；传 None 恢复使用真实 LLM。"""
    global _override
    _override = model
    get_chat_model.cache_clear()


@lru_cache(maxsize=1)
def get_chat_model() -> BaseChatModel:
    """返回 LangChain ChatModel 单例。"""
    if _override is not None:
        return _override

    if not settings.LLM_API_KEY:
        raise BizException(
            code=5010,
            message="LLM_API_KEY 未配置，请在 .env 中设置 DashScope API Key",
        )

    return ChatOpenAI(
        model=settings.LLM_MODEL,
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        temperature=0.1,
        timeout=30,
        max_retries=1,
    )
