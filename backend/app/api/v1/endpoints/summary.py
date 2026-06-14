"""Summary Agent 接口（Phase 10）。

GET /agent/summary?type=daily&date=2026-06-03   → 指定日期的日报
GET /agent/summary?type=weekly&week_start=2026-06-01 → 指定周的周报
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.summary_agent import (
    AssigneeCount,
    SummaryRunResult,
    TaskStats,
    TypeCount,
    run_summary,
)
from app.api.deps import db_session, get_current_user
from app.core.response import success
from app.schemas.summary import (
    AssigneeCountOut,
    SummaryResponse,
    TaskStatsOut,
    TypeCountOut,
)
from app.services.auth_service import CurrentUser

router = APIRouter(prefix="/agent", tags=["agent"])


def _to_dt(d: date) -> datetime:
    """date → UTC midnight datetime。"""
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _stats_to_out(stats: TaskStats) -> TaskStatsOut:
    return TaskStatsOut(
        date_range=stats.date_range,
        total_created=stats.total_created,
        total_completed=stats.total_completed,
        total_overdue=stats.total_overdue,
        total_cancelled=stats.total_cancelled,
        total_high_risk=stats.total_high_risk,
        total_pending_review=stats.total_pending_review,
        total_knowledge_gap=stats.total_knowledge_gap,
        by_type=[TypeCountOut(type=tc.type, count=tc.count) for tc in stats.by_type],
        by_assignee=[
            AssigneeCountOut(
                assignee_id=ac.assignee_id,
                name=ac.name,
                total=ac.total,
                completed=ac.completed,
                overdue=ac.overdue,
            )
            for ac in stats.by_assignee
        ],
    )


@router.get("/summary", summary="生成日报或周报（Phase 10）")
async def get_summary(
    type: str = Query(default="daily", pattern="^(daily|weekly)$", description="报告类型：daily | weekly"),
    date: str = Query(
        default=None,
        description="日报日期，格式 YYYY-MM-DD（不传则取今日）",
    ),
    week_start: str = Query(
        default=None,
        description="周报起始日期，格式 YYYY-MM-DD（不传则取本周一）",
    ),
    write_notif: bool = Query(default=True, description="是否写入通知记录"),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    """实时查询统计数据并调用 LLM 生成自然语言报告。

    - `type=daily`：对 `date` 当天（00:00-次日00:00）进行统计
    - `type=weekly`：对 `week_start` 开始的 7 天进行统计
    - 结果同时写入 `notifications` 表（`kind=daily_summary/weekly_summary`）供推送
    """
    from datetime import date as date_cls

    today = date_cls.today()

    if type == "daily":
        target_date = date_cls.fromisoformat(date) if date else today
        date_start = _to_dt(target_date)
        date_end = date_start + timedelta(days=1)
    else:
        if week_start:
            ws = date_cls.fromisoformat(week_start)
        else:
            ws = today - timedelta(days=today.weekday())  # 本周一
        date_start = _to_dt(ws)
        date_end = date_start + timedelta(days=7)

    result: SummaryRunResult = await run_summary(
        session,
        summary_type=type,
        date_start=date_start,
        date_end=date_end,
        write_notif=write_notif,
    )
    if write_notif:
        await session.commit()

    resp = SummaryResponse(
        summary_type=result.summary_type,
        date_start=result.date_start,
        date_end=result.date_end,
        stats=_stats_to_out(result.stats),
        narrative=result.narrative,
        notification_id=result.notification_id,
    )
    return success(resp.model_dump(mode="json"))
