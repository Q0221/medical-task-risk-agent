"""Risk Agent 单元测试。

覆盖：
- 规则层：类型基线、关键词、优先级 urgent 加权
- LLM 仲裁：LLM 给更高等级时被采用、LLM 给更低等级时被规则层兜底
- LLM 失败：JSON 不合法时 llm_failed=True，等级回落规则层
"""

from __future__ import annotations

import json

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.agents import llm as llm_module
from app.agents.risk_agent import assess_risk
from app.models.enums import RiskLevel, TaskPriority, TaskType
from app.schemas.task import TaskDraft


def _install_fake_llm(messages: list[str]) -> None:
    fake = GenericFakeChatModel(messages=iter([AIMessage(content=m) for m in messages]))
    llm_module.set_chat_model(fake)


def _llm_json(level: str, reason: str = "test", action: str = "test action") -> str:
    return json.dumps(
        {
            "level": level,
            "reason": reason,
            "suggested_action": action,
            "confidence": 0.9,
            "signals": [],
        },
        ensure_ascii=False,
    )


def _draft(
    *,
    title: str = "示例任务",
    type_: TaskType = TaskType.CUSTOMER_FOLLOWUP,
    priority: TaskPriority = TaskPriority.MEDIUM,
    description: str | None = None,
    risk_keywords: list[str] | None = None,
) -> TaskDraft:
    return TaskDraft(
        title=title,
        type=type_,
        priority=priority,
        description=description,
        risk_keywords=risk_keywords or [],
    )


@pytest.fixture(autouse=True)
def _reset_llm():
    yield
    llm_module.set_chat_model(None)


@pytest.mark.asyncio
async def test_rules_low_for_routine_followup() -> None:
    _install_fake_llm([_llm_json(RiskLevel.LOW.value, reason="例行回访")])

    result = await assess_risk(
        _draft(title="回访示例医院的售后情况", type_=TaskType.CUSTOMER_FOLLOWUP)
    )

    assert result.level == RiskLevel.LOW.value
    assert result.rules_level == RiskLevel.LOW.value
    assert result.requires_review is False
    assert result.llm_failed is False


@pytest.mark.asyncio
async def test_rules_adverse_event_baseline_high() -> None:
    _install_fake_llm([_llm_json(RiskLevel.MEDIUM.value, reason="无明确并发症")])

    result = await assess_risk(
        _draft(title="疑似不良反应跟进", type_=TaskType.ADVERSE_EVENT)
    )

    # 类型基线 high；LLM 给 medium，应被规则层兜底
    assert result.rules_level == RiskLevel.HIGH.value
    assert result.level == RiskLevel.HIGH.value
    assert result.requires_review is True


@pytest.mark.asyncio
async def test_keyword_critical_bumps_to_critical() -> None:
    _install_fake_llm([_llm_json(RiskLevel.HIGH.value, reason="患者危重")])

    result = await assess_risk(
        _draft(
            title="患者ICU抢救设备报警",
            type_=TaskType.DEVICE_ANOMALY,
            description="患者已进入ICU，疑似严重并发症",
        )
    )

    assert "icu" in result.matched_keywords or "严重并发症" in result.matched_keywords
    assert result.rules_level == RiskLevel.CRITICAL.value
    assert result.level == RiskLevel.CRITICAL.value
    assert result.requires_review is True


@pytest.mark.asyncio
async def test_urgent_priority_bumps_one_level() -> None:
    _install_fake_llm([_llm_json(RiskLevel.LOW.value, reason="urgent test")])

    result = await assess_risk(
        _draft(
            title="紧急联系客户",
            type_=TaskType.CUSTOMER_FOLLOWUP,
            priority=TaskPriority.URGENT,
        )
    )

    # 类型基线 low + 命中"紧急"关键词（high）+ urgent bump
    assert result.rules_level in (RiskLevel.HIGH.value, RiskLevel.CRITICAL.value)
    assert result.requires_review is True
    assert any(h.startswith("rule_priority_urgent_bump") for h in result.rule_hits)


@pytest.mark.asyncio
async def test_llm_raises_level_above_rules() -> None:
    _install_fake_llm([_llm_json(RiskLevel.HIGH.value, reason="LLM 认为投诉已升级")])

    result = await assess_risk(
        _draft(title="一般客户跟进", type_=TaskType.CUSTOMER_FOLLOWUP)
    )

    assert result.rules_level == RiskLevel.LOW.value
    assert result.level == RiskLevel.HIGH.value
    assert result.llm is not None
    assert result.llm.level == RiskLevel.HIGH.value
    assert result.requires_review is True


@pytest.mark.asyncio
async def test_llm_invalid_falls_back_to_rules() -> None:
    _install_fake_llm(["this is not json"])

    result = await assess_risk(
        _draft(title="设备运行异常，请尽快处理", type_=TaskType.DEVICE_ANOMALY)
    )

    assert result.llm_failed is True
    assert result.llm is None
    assert result.level == result.rules_level
    # 类型基线 medium + 关键词"异常"=medium，最终 medium（不命中"设备故障"也不命中"紧急"）
    assert result.level == RiskLevel.MEDIUM.value
    assert result.requires_review is False
