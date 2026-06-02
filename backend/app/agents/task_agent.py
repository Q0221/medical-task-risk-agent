"""Task Agent：自然语言 → 结构化 TaskDraft。

流程：
    1) 用 system + user prompt 调 LLM。
    2) 抽取 JSON、jsonschema 校验。
    3) 校验失败则用 Self-Reflection prompt 让 LLM 修正，最多重试 N 次。
    4) 成功则返回 (TaskDraft, retry_count)。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from app.agents.llm import get_chat_model
from app.agents.prompts import (
    REFLECTION_USER_TMPL,
    TASK_EXTRACTION_SYSTEM,
    TASK_EXTRACTION_USER_TMPL,
)
from app.agents.schemas import validate_task_draft
from app.core.exceptions import BizException
from app.core.logger import get_logger
from app.schemas.task import TaskDraft

logger = get_logger(__name__)


MAX_RETRIES = 2


@dataclass
class TaskExtractionResult:
    draft: TaskDraft
    raw: dict
    retry_count: int


async def extract_task(
    user_input: str,
    *,
    now: Optional[datetime] = None,
) -> TaskExtractionResult:
    """调 LLM 抽取任务字段，返回 TaskDraft；失败时抛 BizException。"""
    if not user_input.strip():
        raise BizException(code=4001, message="user_input 不能为空")

    llm = get_chat_model()
    current_time = (now or datetime.now()).strftime("%Y-%m-%dT%H:%M:%S")

    sys_msg = SystemMessage(content=TASK_EXTRACTION_SYSTEM)
    first_user_msg = HumanMessage(
        content=TASK_EXTRACTION_USER_TMPL.format(now=current_time, user_input=user_input)
    )
    messages = [sys_msg, first_user_msg]

    last_raw_text = ""
    for attempt in range(MAX_RETRIES + 1):
        logger.info("task_agent attempt=%s", attempt)
        try:
            response = await llm.ainvoke(messages)
        except Exception as exc:
            logger.exception("LLM invocation failed at attempt %s", attempt)
            raise BizException(code=5011, message=f"LLM 调用失败：{exc}") from exc

        last_raw_text = _get_text(response)
        parsed, parse_error = _safe_parse_json(last_raw_text)

        if parsed is None:
            errors = [f"JSON 解析失败：{parse_error}"]
        else:
            errors = validate_task_draft(parsed)

        if not errors:
            try:
                draft = TaskDraft.model_validate(parsed)
            except ValidationError as e:
                errors = [f"Pydantic 校验失败：{e}"]
            else:
                return TaskExtractionResult(
                    draft=draft, raw=parsed, retry_count=attempt
                )

        logger.warning("task_agent attempt=%s errors=%s", attempt, errors)
        if attempt >= MAX_RETRIES:
            break

        messages.append(response)
        messages.append(
            HumanMessage(
                content=REFLECTION_USER_TMPL.format(
                    errors="\n".join(f"- {e}" for e in errors),
                    previous_output=last_raw_text or "(空)",
                )
            )
        )

    raise BizException(
        code=4220,
        message="Agent 多次尝试后仍未生成合法任务草稿，请人工确认或重新描述",
        data={"last_raw": last_raw_text, "errors": errors},
    )


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _get_text(message) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, list):
        # langchain 有时把 content 拆成多个 segment
        return "".join(seg.get("text", "") if isinstance(seg, dict) else str(seg) for seg in content)
    return str(content)


def _safe_parse_json(text: str) -> tuple[Optional[dict], Optional[str]]:
    """容错地从 LLM 输出中抽 JSON：先尝试整段，再剥围栏，最后抠第一个 `{...}`。"""
    text = text.strip()
    if not text:
        return None, "empty response"

    candidates: list[str] = [text]
    fence_match = _JSON_FENCE_RE.search(text)
    if fence_match:
        candidates.append(fence_match.group(1).strip())

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        candidates.append(text[first_brace : last_brace + 1])

    last_error = ""
    for c in candidates:
        try:
            return json.loads(c), None
        except json.JSONDecodeError as e:
            last_error = str(e)
            continue
    return None, last_error
