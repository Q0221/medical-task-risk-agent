"""Task Agent：自然语言 → 意图识别 + 结构化 TaskDraft。

流程：
    1) LLM 同时完成意图识别 + 字段抽取（单次调用）。
    2) JSON Schema 校验；失败则 Self-Reflection 重试（最多 MAX_RETRIES 次）。
    3) 根据 intent 返回不同结果类型：
       - IntentResult    : chitchat / query_task（不建任务，附友好回复）
       - ClarifyResult   : 字段缺失，需追问用户
       - TaskExtractionResult : 字段完整，可直接落库
    4) 多轮追问时，调 merge_clarification 把用户回答合并回草稿。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from app.agents.llm import get_chat_model
from app.agents.prompts import (
    CLARIFY_MERGE_SYSTEM,
    CLARIFY_MERGE_USER_TMPL,
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

# 业务上必须有的字段（无法从输入推断时必须追问）
_REQUIRED_BUSINESS_FIELDS = ["assignee_name"]


# ---------------------------------------------------------------------------
# 返回值类型
# ---------------------------------------------------------------------------

@dataclass
class IntentResult:
    """用户意图不是建任务（闲聊、查询等），附带友好回复。"""
    intent: str          # chitchat | query_task | unclear
    reply: str           # 给用户展示的回复


@dataclass
class ClarifyResult:
    """任务意图明确，但有业务必填字段缺失，需多轮追问。"""
    intent: str = "need_clarify"
    draft_raw: dict = field(default_factory=dict)        # 当前草稿（含 null 字段）
    clarify_fields: list[str] = field(default_factory=list)
    clarify_questions: dict[str, str] = field(default_factory=dict)

    @property
    def first_question(self) -> str:
        """返回第一个需追问的问题。"""
        if self.clarify_fields and self.clarify_questions:
            return self.clarify_questions.get(self.clarify_fields[0], "请补充必要信息。")
        return "请补充必要信息。"

    @property
    def pending_field(self) -> Optional[str]:
        return self.clarify_fields[0] if self.clarify_fields else None


@dataclass
class TaskExtractionResult:
    """字段完整，可以直接落库。"""
    draft: TaskDraft
    raw: dict
    retry_count: int


# ---------------------------------------------------------------------------
# 主入口：首轮抽取
# ---------------------------------------------------------------------------

async def extract_task(
    user_input: str,
    *,
    now: Optional[datetime] = None,
    user_id: Optional[int] = None,
) -> IntentResult | ClarifyResult | TaskExtractionResult:
    """调 LLM 进行意图识别 + 字段抽取，返回三类结果之一。"""
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
    errors: list[str] = []

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
            result = _dispatch(parsed, user_id=user_id, retry_count=attempt)
            if result is not None:
                return result
            # _dispatch 返回 None 表示 create_task 但 Pydantic 校验失败，继续 retry
            errors = ["Pydantic 校验失败，请重新生成合法任务草稿"]

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


# ---------------------------------------------------------------------------
# 多轮追问：合并用户回答回草稿
# ---------------------------------------------------------------------------

async def merge_clarification(
    draft_raw: dict,
    question: str,
    user_answer: str,
    *,
    user_id: Optional[int] = None,
) -> ClarifyResult | TaskExtractionResult:
    """把用户对追问的回答合并回 draft_raw，返回更新后的结果。"""
    llm = get_chat_model()

    messages = [
        SystemMessage(content=CLARIFY_MERGE_SYSTEM),
        HumanMessage(
            content=CLARIFY_MERGE_USER_TMPL.format(
                draft_json=json.dumps(draft_raw, ensure_ascii=False, indent=2),
                question=question,
                user_answer=user_answer,
            )
        ),
    ]

    last_raw_text = ""
    for attempt in range(MAX_RETRIES + 1):
        logger.info("merge_clarification attempt=%s", attempt)
        try:
            response = await llm.ainvoke(messages)
        except Exception as exc:
            logger.exception("LLM invocation failed in merge_clarification attempt %s", attempt)
            raise BizException(code=5011, message=f"LLM 调用失败：{exc}") from exc

        last_raw_text = _get_text(response)
        parsed, parse_error = _safe_parse_json(last_raw_text)

        if parsed is None:
            errors = [f"JSON 解析失败：{parse_error}"]
        else:
            errors = validate_task_draft(parsed)

        if not errors:
            result = _dispatch(parsed, user_id=user_id, retry_count=attempt)
            if result is not None:
                return result
            errors = ["Pydantic 校验失败，请重新生成合法任务草稿"]

        logger.warning("merge_clarification attempt=%s errors=%s", attempt, errors)
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

    # 合并失败时回退到原草稿继续追问第一个字段
    logger.warning("merge_clarification failed after retries, keeping original draft")
    clarify_fields = draft_raw.get("clarify_fields") or _REQUIRED_BUSINESS_FIELDS
    clarify_questions = draft_raw.get("clarify_questions") or {
        "assignee_name": "请问这个任务由谁来负责处理？"
    }
    return ClarifyResult(
        draft_raw=draft_raw,
        clarify_fields=clarify_fields,
        clarify_questions=clarify_questions,
    )


# ---------------------------------------------------------------------------
# 内部：根据解析结果分发
# ---------------------------------------------------------------------------

def _dispatch(
    parsed: dict,
    *,
    user_id: Optional[int],
    retry_count: int,
) -> Optional[IntentResult | ClarifyResult | TaskExtractionResult]:
    """根据 intent 字段分发到对应结果类型。返回 None 表示 Pydantic 校验失败需继续重试。"""
    intent = parsed.get("intent", "create_task")

    # ── 非建任务意图 ──
    if intent in ("chitchat", "query_task", "unclear"):
        reply = parsed.get("reply") or _default_non_task_reply(intent)
        return IntentResult(intent=intent, reply=reply)

    # ── 建任务意图：检查业务必填字段 ──
    clarify_fields: list[str] = parsed.get("clarify_fields") or []
    clarify_questions: dict = parsed.get("clarify_questions") or {}

    # 若 LLM 未把缺失字段加入 clarify_fields，我们也做兜底检查
    assignee = parsed.get("assignee_name")
    if assignee is None and user_id is None and "assignee_name" not in clarify_fields:
        clarify_fields.append("assignee_name")
        if "assignee_name" not in clarify_questions:
            clarify_questions["assignee_name"] = "请问这个任务由谁来负责处理？"

    if clarify_fields:
        return ClarifyResult(
            draft_raw=parsed,
            clarify_fields=clarify_fields,
            clarify_questions=clarify_questions,
        )

    # ── 字段完整，尝试 Pydantic 校验 ──
    # 处理 __self__ 占位符（用户说"我来负责"）
    if parsed.get("assignee_name") == "__self__":
        parsed["assignee_name"] = None  # 由上层用 user_id 对应的用户填入

    try:
        draft = TaskDraft.model_validate(_to_draft_input(parsed))
        return TaskExtractionResult(draft=draft, raw=parsed, retry_count=retry_count)
    except ValidationError:
        logger.warning("Pydantic validation failed for parsed=%s", parsed)
        return None


def _to_draft_input(parsed: dict) -> dict:
    """从 LLM 输出的完整 JSON 中提取 TaskDraft 所需的字段子集。"""
    _DRAFT_KEYS = {
        "title", "type", "priority", "description",
        "assignee_name", "hospital_name", "product_name",
        "business_object_type", "business_object_id",
        "remind_at", "due_at", "risk_keywords",
    }
    result = {k: parsed.get(k) for k in _DRAFT_KEYS}
    # 缺省值
    if not result.get("type"):
        result["type"] = "other"
    if not result.get("priority"):
        result["priority"] = "medium"
    if not result.get("business_object_type"):
        result["business_object_type"] = "none"
    if result.get("risk_keywords") is None:
        result["risk_keywords"] = []
    return result


def _default_non_task_reply(intent: str) -> str:
    if intent == "query_task":
        return "您可以通过 GET /api/v1/tasks 接口查询任务列表，支持按负责人、状态、风险等级筛选。"
    if intent == "unclear":
        return "我是医疗任务协同助手，专注于帮您创建和跟进工作任务。请描述您需要处理的事项（例如：请张客服明天下午跟进某医院的售后情况）。"
    return "您好！我是医疗任务协同助手，专注于帮您管理工作任务。请告诉我需要创建什么任务？"


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _get_text(message) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, list):
        return "".join(
            seg.get("text", "") if isinstance(seg, dict) else str(seg)
            for seg in content
        )
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
