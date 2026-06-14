"""Agent 字段抽取的 JSON Schema 与校验工具。

Schema 关键约束：
- 必填字段：title / type / priority / business_object_type / risk_keywords
- 枚举字段：type / priority / business_object_type
- 时间字段：remind_at / due_at，ISO 8601 字符串（datetime 子集）
"""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator
from jsonschema import exceptions as js_exc

from app.models.enums import BusinessObjectType, RiskLevel, TaskPriority, TaskType


TASK_DRAFT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "intent",
        "reply",
        "clarify_fields",
        "clarify_questions",
        "title",
        "type",
        "priority",
        "business_object_type",
        "risk_keywords",
    ],
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["create_task", "query_task", "chitchat", "unclear"],
        },
        "reply": {"type": ["string", "null"], "maxLength": 300},
        "clarify_fields": {
            "type": "array",
            "items": {"type": "string"},
        },
        "clarify_questions": {
            "type": ["object", "null"],
            "additionalProperties": {"type": "string"},
        },
        "title": {"type": ["string", "null"], "maxLength": 100},
        "type": {
            "type": ["string", "null"],
            "enum": [e.value for e in TaskType] + [None],
        },
        "priority": {
            "type": ["string", "null"],
            "enum": [e.value for e in TaskPriority] + [None],
        },
        "description": {"type": ["string", "null"]},
        "assignee_name": {"type": ["string", "null"]},
        "hospital_name": {"type": ["string", "null"]},
        "product_name": {"type": ["string", "null"]},
        "business_object_type": {
            "type": ["string", "null"],
            "enum": [e.value for e in BusinessObjectType] + [None],
        },
        "business_object_id": {"type": ["string", "null"]},
        "remind_at": {
            "type": ["string", "null"],
            "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$",
        },
        "due_at": {
            "type": ["string", "null"],
            "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$",
        },
        "risk_keywords": {
            "type": ["array", "null"],
            "items": {"type": "string"},
        },
        # ── query_task 专用参数（其他 intent 时为 null / 缺省）──
        "query_assignee": {"type": ["string", "null"]},
        "query_mine": {"type": ["boolean", "null"]},
        "query_status": {
            "type": ["string", "null"],
            "enum": ["pending", "in_progress", "completed", "awaiting_review", "cancelled", None],
        },
        "query_risk": {
            "type": ["string", "null"],
            "enum": [e.value for e in RiskLevel] + [None],
        },
        "query_overdue": {"type": ["boolean", "null"]},
        "query_due_today": {"type": ["boolean", "null"]},
        "query_due_this_week": {"type": ["boolean", "null"]},
        "query_limit": {"type": ["integer", "null"], "minimum": 1, "maximum": 20},
    },
}


_validator = Draft202012Validator(TASK_DRAFT_SCHEMA)


def validate_task_draft(data: Any) -> list[str]:
    """返回错误信息列表；空列表表示通过校验。"""
    if not isinstance(data, dict):
        return [f"top-level must be a JSON object, got {type(data).__name__}"]
    errors: list[str] = []
    for err in _validator.iter_errors(data):
        path = ".".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"{path}: {err.message}")
    return errors


def assert_valid(data: Any) -> None:
    """校验失败抛出 jsonschema.ValidationError。"""
    _validator.validate(data)


RISK_ASSESSMENT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["level", "reason", "suggested_action", "confidence", "signals"],
    "properties": {
        "level": {"type": "string", "enum": [e.value for e in RiskLevel]},
        "reason": {"type": "string", "maxLength": 500},
        "suggested_action": {"type": "string", "maxLength": 500},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "signals": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 10,
        },
    },
}


_risk_validator = Draft202012Validator(RISK_ASSESSMENT_SCHEMA)


def validate_risk_assessment(data: Any) -> list[str]:
    """返回错误信息列表；空列表表示通过校验。"""
    if not isinstance(data, dict):
        return [f"top-level must be a JSON object, got {type(data).__name__}"]
    errors: list[str] = []
    for err in _risk_validator.iter_errors(data):
        path = ".".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"{path}: {err.message}")
    return errors


__all__ = [
    "TASK_DRAFT_SCHEMA",
    "RISK_ASSESSMENT_SCHEMA",
    "validate_task_draft",
    "validate_risk_assessment",
    "assert_valid",
    "js_exc",
]
