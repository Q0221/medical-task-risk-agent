"""Risk Agent 医疗风控专家节点。

混合策略：
    1. **规则层**：任务类型基线 + 关键词词典 + 优先级加权，给出 rules_level
                  与命中明细，速度快、零成本、可解释。
    2. **LLM 层**：把任务草稿 + 规则层结果一并喂给 LLM，让它输出
                  level / reason / suggested_action / confidence / signals。
                  失败（API 异常 / JSON 校验失败）时退化为仅用规则层。
    3. **仲裁**：final_level = max(rules_level, llm_level)（保守取高），
                reason / suggested_action 优先用 LLM，再以规则原因兜底。

返回 `RiskAssessment` Pydantic 模型，由 risk_service 负责持久化。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from app.agents.llm import get_chat_model
from app.agents.prompts import (
    RISK_ASSESSMENT_SYSTEM,
    RISK_ASSESSMENT_USER_TMPL,
)
from app.agents.schemas import validate_risk_assessment
from app.core.logger import get_logger
from app.models.enums import RiskLevel, TaskPriority, TaskType
from app.schemas.risk import LLMRiskJudgement, RiskAssessment
from app.schemas.task import TaskDraft

logger = get_logger(__name__)


# ---------- 规则层配置 ----------

_TYPE_BASELINE: dict[str, RiskLevel] = {
    TaskType.ADVERSE_EVENT.value: RiskLevel.HIGH,
    TaskType.DEVICE_ANOMALY.value: RiskLevel.MEDIUM,
    TaskType.COMPLAINT.value: RiskLevel.MEDIUM,
    TaskType.COMPLIANCE_REVIEW.value: RiskLevel.MEDIUM,
    TaskType.PRODUCT_FEEDBACK.value: RiskLevel.LOW,
    TaskType.CUSTOMER_FOLLOWUP.value: RiskLevel.LOW,
    TaskType.KNOWLEDGE_MAINTAIN.value: RiskLevel.LOW,
    TaskType.OTHER.value: RiskLevel.LOW,
}

# 关键词词典（值 = 命中后建议的最低等级）
_KEYWORD_LEVEL: dict[str, RiskLevel] = {
    # critical
    "死亡": RiskLevel.CRITICAL,
    "致死": RiskLevel.CRITICAL,
    "致残": RiskLevel.CRITICAL,
    "危重": RiskLevel.CRITICAL,
    "重症": RiskLevel.CRITICAL,
    "icu": RiskLevel.CRITICAL,
    "患者伤害": RiskLevel.CRITICAL,
    "严重并发症": RiskLevel.CRITICAL,
    "严重并发": RiskLevel.CRITICAL,
    "患者安全": RiskLevel.CRITICAL,
    # high
    "不良事件": RiskLevel.HIGH,
    "投诉升级": RiskLevel.HIGH,
    "升级投诉": RiskLevel.HIGH,
    "设备故障": RiskLevel.HIGH,
    "停机": RiskLevel.HIGH,
    "停诊": RiskLevel.HIGH,
    "召回": RiskLevel.HIGH,
    "合规违规": RiskLevel.HIGH,
    "违规": RiskLevel.HIGH,
    "诉讼": RiskLevel.HIGH,
    "紧急": RiskLevel.HIGH,
    # medium
    "投诉": RiskLevel.MEDIUM,
    "异常": RiskLevel.MEDIUM,
    "故障": RiskLevel.MEDIUM,
    "报警": RiskLevel.MEDIUM,
    "客诉": RiskLevel.MEDIUM,
    "隐患": RiskLevel.MEDIUM,
    "纠纷": RiskLevel.MEDIUM,
    "差评": RiskLevel.MEDIUM,
}

_LEVEL_ORDER: List[RiskLevel] = [
    RiskLevel.LOW,
    RiskLevel.MEDIUM,
    RiskLevel.HIGH,
    RiskLevel.CRITICAL,
]
_LEVEL_RANK: dict[str, int] = {lvl.value: i for i, lvl in enumerate(_LEVEL_ORDER)}


def _rank(level) -> int:
    return _LEVEL_RANK[_value(level)]


def _value(level) -> str:
    return level.value if hasattr(level, "value") else str(level)


def _max_level(*levels) -> RiskLevel:
    best = RiskLevel.LOW
    for lvl in levels:
        if lvl is None:
            continue
        if _rank(lvl) > _rank(best):
            best = RiskLevel(_value(lvl))
    return best


def _bump(level: RiskLevel, by: int = 1) -> RiskLevel:
    """向上升档；不超过 critical。"""
    idx = min(len(_LEVEL_ORDER) - 1, _rank(level) + by)
    return _LEVEL_ORDER[idx]


# ---------- 规则层实现 ----------


@dataclass
class _RulesResult:
    type_baseline: RiskLevel
    matched_keywords: List[str]
    rule_hits: List[str]
    rules_level: RiskLevel
    reasons: List[str]


def _scan_keywords(text: str) -> List[Tuple[str, RiskLevel]]:
    if not text:
        return []
    low = text.lower()
    hits: list[tuple[str, RiskLevel]] = []
    for kw, level in _KEYWORD_LEVEL.items():
        if kw in low:
            hits.append((kw, level))
    return hits


def _run_rules(draft: TaskDraft) -> _RulesResult:
    type_value = _value(draft.type) if draft.type else TaskType.OTHER.value
    type_baseline = _TYPE_BASELINE.get(type_value, RiskLevel.LOW)

    haystack_parts: list[str] = [draft.title or ""]
    if draft.description:
        haystack_parts.append(draft.description)
    if draft.risk_keywords:
        haystack_parts.extend(draft.risk_keywords)
    haystack = "\n".join(haystack_parts)

    kw_hits = _scan_keywords(haystack)
    matched_keywords = sorted({kw for kw, _ in kw_hits})
    kw_level = RiskLevel.LOW
    for _, lvl in kw_hits:
        if _rank(lvl) > _rank(kw_level):
            kw_level = lvl

    rule_hits: list[str] = []
    reasons: list[str] = []

    rule_hits.append(f"rule_type_baseline:{type_value}->{type_baseline.value}")
    reasons.append(f"任务类型 {type_value} 基线 {type_baseline.value}")

    if matched_keywords:
        rule_hits.append("rule_keyword_hit")
        reasons.append(
            f"命中关键词 {matched_keywords}（推导等级 {kw_level.value}）"
        )

    rules_level = _max_level(type_baseline, kw_level)

    # 优先级 urgent 至少 medium，并在已有等级上 +1 档
    if _value(draft.priority) == TaskPriority.URGENT.value:
        bumped = _bump(rules_level, by=1)
        if _rank(bumped) > _rank(rules_level):
            rule_hits.append("rule_priority_urgent_bump")
            reasons.append(f"优先级 urgent，从 {rules_level.value} 升至 {bumped.value}")
            rules_level = bumped

    return _RulesResult(
        type_baseline=type_baseline,
        matched_keywords=matched_keywords,
        rule_hits=rule_hits,
        rules_level=rules_level,
        reasons=reasons,
    )


# ---------- LLM 层实现 ----------

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _get_text(message) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, list):
        return "".join(
            seg.get("text", "") if isinstance(seg, dict) else str(seg) for seg in content
        )
    return str(content)


def _safe_parse_json(text: str) -> Optional[dict]:
    text = (text or "").strip()
    if not text:
        return None
    candidates: list[str] = [text]
    fence = _JSON_FENCE_RE.search(text)
    if fence:
        candidates.append(fence.group(1).strip())
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last > first:
        candidates.append(text[first : last + 1])
    for c in candidates:
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    return None


async def _call_llm(draft: TaskDraft, rules: _RulesResult) -> Optional[LLMRiskJudgement]:
    try:
        llm = get_chat_model()
    except Exception as exc:
        logger.warning("risk_agent LLM unavailable, fallback to rules-only: %s", exc)
        return None

    task_draft_json = json.dumps(draft.model_dump(mode="json"), ensure_ascii=False)
    user_msg = RISK_ASSESSMENT_USER_TMPL.format(
        task_draft_json=task_draft_json,
        rules_level=rules.rules_level.value,
        type_baseline=rules.type_baseline.value,
        matched_keywords=rules.matched_keywords or [],
        rule_hits=rules.rule_hits or [],
    )

    messages = [SystemMessage(content=RISK_ASSESSMENT_SYSTEM), HumanMessage(content=user_msg)]

    try:
        response = await llm.ainvoke(messages)
    except Exception as exc:
        logger.exception("risk_agent LLM invocation failed: %s", exc)
        return None

    parsed = _safe_parse_json(_get_text(response))
    if parsed is None:
        logger.warning("risk_agent LLM output not JSON parseable")
        return None

    errors = validate_risk_assessment(parsed)
    if errors:
        logger.warning("risk_agent LLM output schema invalid: %s", errors)
        return None

    try:
        return LLMRiskJudgement.model_validate(parsed)
    except ValidationError as e:
        logger.warning("risk_agent LLM output pydantic invalid: %s", e)
        return None


# ---------- 仲裁 + 对外入口 ----------


def _compose_reason(rules: _RulesResult, llm: Optional[LLMRiskJudgement]) -> str:
    parts: list[str] = []
    if llm and llm.reason:
        parts.append(f"[LLM] {llm.reason}")
    if rules.reasons:
        parts.append("[规则] " + "；".join(rules.reasons))
    return "\n".join(parts) if parts else "未发现明显风险信号"


def _compose_action(rules: _RulesResult, llm: Optional[LLMRiskJudgement], final: RiskLevel) -> str:
    if llm and llm.suggested_action:
        return llm.suggested_action
    if final in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        return "建议立即升级至质控 / 合规主管复核，并通知相关责任人。"
    if final == RiskLevel.MEDIUM:
        return "建议在 24 小时内跟进，必要时升级。"
    return "按常规流程跟进。"


async def assess_risk(draft: TaskDraft) -> RiskAssessment:
    """风险评估主入口：规则 → LLM → 仲裁。
    
    任何异常都会被吞掉，最差情况下返回纯规则层结果（llm_failed=True）。
    """
    if draft is None:
        raise ValueError("draft must not be None")

    rules = _run_rules(draft)
    llm = await _call_llm(draft, rules)

    final_level = _max_level(rules.rules_level, llm.level if llm else None)
    reason = _compose_reason(rules, llm)
    action = _compose_action(rules, llm, final_level)
    requires_review = final_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    return RiskAssessment(
        level=final_level,
        reason=reason,
        suggested_action=action,
        requires_review=requires_review,
        rules_level=rules.rules_level,
        type_baseline=rules.type_baseline,
        matched_keywords=rules.matched_keywords,
        rule_hits=rules.rule_hits,
        llm=llm,
        llm_failed=llm is None,
    )


# 暴露给测试 / 集成需要的内部工具
__all__ = [
    "assess_risk",
]


def _exposed_for_tests():
    """方便单测直接调规则层。"""
    return _run_rules
