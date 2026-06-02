"""Task Agent 单元测试：用 FakeLLM 替换真实大模型。

不依赖 MySQL / Redis / 真实 LLM。
"""

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.agents import llm as llm_module
from app.agents.task_agent import extract_task
from app.core.exceptions import BizException


VALID_JSON = """{
  "title": "回访示例三甲医院A售后",
  "type": "customer_followup",
  "priority": "medium",
  "description": "明天下午3点提醒回访",
  "assignee_name": "张客服",
  "hospital_name": "示例三甲医院A",
  "product_name": null,
  "business_object_type": "hospital",
  "business_object_id": null,
  "remind_at": "2026-06-03T15:00:00",
  "due_at": null,
  "risk_keywords": []
}"""

INVALID_THEN_VALID = [
    "这不是 JSON，请重试。",
    VALID_JSON,
]


def _install_fake_llm(messages: list[str]) -> None:
    """注入一个按序返回固定文本的 FakeLLM。"""
    fake = GenericFakeChatModel(messages=iter([AIMessage(content=m) for m in messages]))
    llm_module.set_chat_model(fake)


@pytest.fixture(autouse=True)
def _reset_llm():
    yield
    llm_module.set_chat_model(None)


@pytest.mark.asyncio
async def test_extract_task_happy_path() -> None:
    _install_fake_llm([VALID_JSON])

    result = await extract_task("请张客服明天下午3点提醒回访示例三甲医院A的售后情况")

    assert result.retry_count == 0
    assert result.draft.title.startswith("回访")
    assert result.draft.assignee_name == "张客服"
    assert result.draft.hospital_name == "示例三甲医院A"
    assert result.draft.business_object_type == "hospital"
    assert result.draft.remind_at is not None


@pytest.mark.asyncio
async def test_extract_task_self_reflection_recovers() -> None:
    _install_fake_llm(INVALID_THEN_VALID)

    result = await extract_task("请张客服明天提醒回访")

    assert result.retry_count == 1
    assert result.draft.title


@pytest.mark.asyncio
async def test_extract_task_gives_up_after_max_retries() -> None:
    _install_fake_llm(["bad"] * 5)

    with pytest.raises(BizException) as exc_info:
        await extract_task("瞎写一条")

    assert exc_info.value.code == 4220
