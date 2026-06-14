"""任务标题明确性规则单元测试（不依赖 LLM / DB）。"""

import pytest

from app.agents.task_agent import (
    IntentResult,
    _apply_title_merge_fallback,
    _dispatch,
    _needs_task_detail,
    _normalize_clarification,
)


def _draft(**overrides) -> dict:
    base = {
        "intent": "create_task",
        "clarify_fields": [],
        "clarify_questions": {},
        "title": None,
        "type": "customer_followup",
        "priority": "medium",
        "description": None,
        "assignee_name": "张客服",
        "hospital_name": None,
        "due_at": "2026-06-04T15:00:00",
        "remind_at": None,
        "business_object_type": "hospital",
        "risk_keywords": [],
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "title,expected",
    [
        ("跟进医院的回访", True),
        ("处理一下", True),
        ("跟进医院A", True),
        ("设备使用状况", False),
        ("医院设备使用状况的回访", False),
        ("回访医院A试用反馈", False),
        ("示例三甲医院A设备使用状况回访", False),
    ],
)
def test_needs_task_detail_cases(title: str, expected: bool) -> None:
    parsed = _draft(title=title)
    assert _needs_task_detail(parsed) is expected


def test_needs_task_detail_respects_llm_when_title_filled() -> None:
    parsed = _draft(title="医院设备使用状况的回访", clarify_fields=[])
    assert _needs_task_detail(parsed, respect_llm=True) is False


def test_needs_task_detail_respects_llm_blocks_pure_vague() -> None:
    parsed = _draft(title="处理一下", clarify_fields=[])
    assert _needs_task_detail(parsed, respect_llm=True) is True


def test_normalize_clarification_trusts_llm_title_judgment() -> None:
    parsed = _draft(
        title="医院设备使用状况的回访",
        clarify_fields=[],
        assignee_name=None,
    )
    fields, _ = _normalize_clarification(parsed)
    assert "title" not in fields
    assert "assignee_name" in fields


def test_normalize_clarification_still_requires_vague_title() -> None:
    parsed = _draft(title="跟进医院的回访", clarify_fields=[])
    fields, _ = _normalize_clarification(parsed)
    assert fields[0] == "title"


def test_apply_title_merge_fallback_writes_user_answer() -> None:
    draft_raw = _draft(title="跟进医院的回访", hospital_name="示例三甲医院A")
    merged = _apply_title_merge_fallback(
        dict(draft_raw),
        pending_field="title",
        user_answer="设备使用状况",
        draft_raw=draft_raw,
    )
    assert merged["title"] == "示例三甲医院A设备使用状况"
    assert _needs_task_detail(merged) is False


def test_apply_title_merge_fallback_keeps_full_user_title() -> None:
    draft_raw = _draft(title="跟进医院的回访")
    merged = _apply_title_merge_fallback(
        dict(draft_raw),
        pending_field="title",
        user_answer="医院设备使用状况的回访",
        draft_raw=draft_raw,
    )
    assert merged["title"] == "医院设备使用状况的回访"
    assert _needs_task_detail(merged) is False


def test_dispatch_query_task_skips_title_rules() -> None:
    parsed = {
        "intent": "query_task",
        "reply": "正在查询张客服的待办任务。",
        "clarify_fields": [],
        "clarify_questions": {},
        "title": None,
        "query_assignee": "张客服",
        "query_status": "pending",
    }
    result = _dispatch(parsed, user_id=1, retry_count=0)
    assert isinstance(result, IntentResult)
    assert result.intent == "query_task"
