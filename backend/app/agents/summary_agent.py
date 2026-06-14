"""Summary Agent（Phase 10）：日报 / 周报统计与 LLM 叙述生成。

流程：
  1. collect_stats(session, date_start, date_end) → TaskStats
     · 查询该时段内新增、完成、逾期、高风险、待审核等各维度数量
     · 按任务类型、状态分组统计
     · 按负责人 Top-N 统计
  2. generate_narrative(stats, summary_type) → str
     · 将统计数据序列化为 JSON 发给 LLM，请求生成自然语言报告
     · LLM 不可用时降级为模板文本
  3. write_notification(session, narrative, summary_type, notify_channel)
     · 将报告写入 notifications 表（kind=daily_summary/weekly_summary）

对外接口：
  run_summary(session, summary_type, date_start, date_end) → SummaryRunResult
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm import get_chat_model
from app.core.config import settings
from app.core.logger import get_logger
from app.models.enums import (
    NotificationChannel,
    NotificationKind,
    NotificationStatus,
    RiskLevel,
    TaskStatus,
    TaskType,
)
from app.models.notification import Notification
from app.models.task import Task
from app.models.user import User

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class TypeCount:
    type: str
    count: int


@dataclass
class AssigneeCount:
    assignee_id: int
    name: str
    total: int
    completed: int
    overdue: int


@dataclass
class TaskStats:
    date_range: str
    total_created: int = 0
    total_completed: int = 0
    total_overdue: int = 0
    total_cancelled: int = 0
    total_high_risk: int = 0        # risk_level in (high, critical)
    total_pending_review: int = 0   # review_status=pending
    total_knowledge_gap: int = 0    # type=knowledge_maintain
    by_type: list[TypeCount] = field(default_factory=list)
    by_assignee: list[AssigneeCount] = field(default_factory=list)


@dataclass
class SummaryRunResult:
    summary_type: str             # "daily" | "weekly"
    date_start: datetime
    date_end: datetime
    stats: TaskStats
    narrative: str
    notification_id: Optional[int] = None


# ---------------------------------------------------------------------------
# 统计收集
# ---------------------------------------------------------------------------

_HIGH_RISK = {RiskLevel.HIGH.value, RiskLevel.CRITICAL.value}


async def collect_stats(
    session: AsyncSession,
    date_start: datetime,
    date_end: datetime,
) -> TaskStats:
    """查询 [date_start, date_end) 区间内的任务统计数据。"""
    date_range = (
        f"{date_start.strftime('%Y-%m-%d')} ~ {date_end.strftime('%Y-%m-%d')}"
    )
    stats = TaskStats(date_range=date_range)

    base_q = select(Task).where(
        Task.created_at >= date_start,
        Task.created_at < date_end,
        Task.deleted_at.is_(None),
    )

    tasks = (await session.execute(base_q)).scalars().all()

    stats.total_created = len(tasks)
    stats.total_completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED.value)
    stats.total_overdue = sum(1 for t in tasks if t.status == TaskStatus.OVERDUE.value)
    stats.total_cancelled = sum(1 for t in tasks if t.status == TaskStatus.CANCELLED.value)
    stats.total_high_risk = sum(1 for t in tasks if t.risk_level in _HIGH_RISK)
    stats.total_pending_review = sum(1 for t in tasks if t.review_status == "pending")
    stats.total_knowledge_gap = sum(1 for t in tasks if t.type == TaskType.KNOWLEDGE_MAINTAIN.value)

    # 按类型统计
    type_count: dict[str, int] = {}
    for t in tasks:
        type_count[t.type] = type_count.get(t.type, 0) + 1
    stats.by_type = [TypeCount(type=k, count=v) for k, v in sorted(type_count.items(), key=lambda x: -x[1])]

    # 按负责人统计（Top 10）
    assignee_ids = list({t.assignee_id for t in tasks if t.assignee_id})
    if assignee_ids:
        users = (
            await session.execute(
                select(User).where(User.id.in_(assignee_ids), User.deleted_at.is_(None))
            )
        ).scalars().all()
        user_map = {u.id: u.name for u in users}

        assignee_data: dict[int, dict] = {}
        for t in tasks:
            aid = t.assignee_id
            if not aid:
                continue
            if aid not in assignee_data:
                assignee_data[aid] = {"total": 0, "completed": 0, "overdue": 0}
            assignee_data[aid]["total"] += 1
            if t.status == TaskStatus.COMPLETED.value:
                assignee_data[aid]["completed"] += 1
            elif t.status == TaskStatus.OVERDUE.value:
                assignee_data[aid]["overdue"] += 1

        stats.by_assignee = sorted(
            [
                AssigneeCount(
                    assignee_id=aid,
                    name=user_map.get(aid, f"user_{aid}"),
                    **data,
                )
                for aid, data in assignee_data.items()
            ],
            key=lambda x: -x.total,
        )[:10]

    return stats


# ---------------------------------------------------------------------------
# LLM 叙述生成
# ---------------------------------------------------------------------------

_SUMMARY_SYSTEM = (
    "你是医疗企业任务协同系统的智能助理，负责根据统计数据生成简洁专业的任务报告。"
    "报告风格：简洁、客观、专业，使用中文，不超过 400 字。"
    "报告结构：①整体概况 ②风险提示 ③负责人情况 ④待处理事项建议。"
)

_SUMMARY_USER = (
    "请根据以下{period}统计数据，生成一份任务报告：\n\n{stats_json}\n\n"
    "要求：按上述四个部分分段，每段 2-3 句话，突出需要关注的异常数据。"
)


async def generate_narrative(stats: TaskStats, summary_type: str) -> str:
    """调用 LLM 生成自然语言报告；失败时返回模板文本。"""
    period = "日报" if summary_type == "daily" else "周报"

    stats_dict = {
        "统计区间": stats.date_range,
        "新增任务": stats.total_created,
        "已完成": stats.total_completed,
        "逾期任务": stats.total_overdue,
        "已取消": stats.total_cancelled,
        "高风险任务": stats.total_high_risk,
        "待人工审核": stats.total_pending_review,
        "知识补充任务": stats.total_knowledge_gap,
        "按类型": [{"类型": tc.type, "数量": tc.count} for tc in stats.by_type],
        "负责人Top10": [
            {"姓名": ac.name, "总计": ac.total, "完成": ac.completed, "逾期": ac.overdue}
            for ac in stats.by_assignee
        ],
    }

    if not settings.LLM_API_KEY:
        return _fallback_narrative(stats, period)

    try:
        llm = get_chat_model()
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(content=_SUMMARY_SYSTEM),
            HumanMessage(
                content=_SUMMARY_USER.format(
                    period=period,
                    stats_json=json.dumps(stats_dict, ensure_ascii=False, indent=2),
                )
            ),
        ]
        resp = await llm.ainvoke(messages)
        narrative = resp.content.strip()
        logger.info("summary narrative generated (%d chars)", len(narrative))
        return narrative
    except Exception as exc:
        logger.warning("LLM summary generation failed, using template: %s", exc)
        return _fallback_narrative(stats, period)


def _fallback_narrative(stats: TaskStats, period: str) -> str:
    lines = [f"【{period}报告】{stats.date_range}"]
    lines.append(
        f"① 整体概况：区间内新增任务 {stats.total_created} 条，"
        f"完成 {stats.total_completed} 条，"
        f"逾期 {stats.total_overdue} 条，"
        f"取消 {stats.total_cancelled} 条。"
    )
    if stats.total_high_risk:
        lines.append(f"② 风险提示：存在 {stats.total_high_risk} 条高风险/严重任务，请及时关注。")
    else:
        lines.append("② 风险提示：无高风险任务，整体风险可控。")
    if stats.total_pending_review:
        lines.append(f"③ 待处理：有 {stats.total_pending_review} 条任务待人工审核，请及时处理。")
    if stats.by_assignee:
        top = stats.by_assignee[0]
        lines.append(f"④ 负责人：{top.name} 任务最多（{top.total} 条），完成率 {int(top.completed/top.total*100) if top.total else 0}%。")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 写通知记录
# ---------------------------------------------------------------------------

async def write_summary_notification(
    session: AsyncSession,
    narrative: str,
    summary_type: str,
    date_range: str,
) -> Optional[int]:
    """将报告写入 notifications 表，供 NotifyWorker 推送。"""
    kind = (
        NotificationKind.DAILY_SUMMARY.value
        if summary_type == "daily"
        else NotificationKind.WEEKLY_SUMMARY.value
    )
    period = "日报" if summary_type == "daily" else "周报"
    notif = Notification(
        task_id=None,
        kind=kind,
        channel=getattr(settings, "DEFAULT_NOTIFY_CHANNEL", NotificationChannel.IM.value),
        recipient_user_id=None,   # 广播，NotifyWorker 按角色发送（未来扩展）
        title=f"任务{period}：{date_range}",
        content=narrative,
        status=NotificationStatus.PENDING.value,
    )
    session.add(notif)
    await session.flush()
    await session.refresh(notif)
    return notif.id


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

async def run_summary(
    session: AsyncSession,
    summary_type: str,
    date_start: datetime,
    date_end: datetime,
    *,
    write_notif: bool = True,
) -> SummaryRunResult:
    """端到端生成报告：统计 → LLM 叙述 → 写通知。"""
    stats = await collect_stats(session, date_start, date_end)
    narrative = await generate_narrative(stats, summary_type)

    notif_id: Optional[int] = None
    if write_notif:
        # 由调用方通过 session.begin() 提交事务；此处仅 flush 获取 ID
        notif_id = await write_summary_notification(session, narrative, summary_type, stats.date_range)

    return SummaryRunResult(
        summary_type=summary_type,
        date_start=date_start,
        date_end=date_end,
        stats=stats,
        narrative=narrative,
        notification_id=notif_id,
    )


__all__ = ["run_summary", "collect_stats", "generate_narrative", "SummaryRunResult", "TaskStats"]
