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

from app.models.enums import BusinessObjectType, TaskPriority, TaskType


TASK_DRAFT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "title",
        "type",
        "priority",
        "business_object_type",
        "risk_keywords",
    ],
    "properties": {
        "title": {"type": "string", "minLength": 1, "maxLength": 100},
        "type": {"type": "string", "enum": [e.value for e in TaskType]},
        "priority": {"type": "string", "enum": [e.value for e in TaskPriority]},
        "description": {"type": ["string", "null"]},
        "assignee_name": {"type": ["string", "null"]},
        "hospital_name": {"type": ["string", "null"]},
        "product_name": {"type": ["string", "null"]},
        "business_object_type": {
            "type": "string",
            "enum": [e.value for e in BusinessObjectType],
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
            "type": "array",
            "items": {"type": "string"},
        },
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


__all__ = [
    "TASK_DRAFT_SCHEMA",
    "validate_task_draft",
    "assert_valid",
    "js_exc",
]
