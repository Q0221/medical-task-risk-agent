"""报告与图表接口。

GET /reports/charts/trend           趋势折线图数据
GET /reports/charts/type            任务类型分布
GET /reports/charts/risk            风险分布
GET /reports/charts/assignee        负责人完成排行
GET /reports/history                历史报告列表（日报/周报通知记录）
GET /reports/history/{id}           报告详情
GET /reports/export/word/{id}       下载 Word 文件
GET /reports/export/pdf/{id}        下载 PDF 文件
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_current_user
from app.core.response import success
from app.services.auth_service import CurrentUser
from app.services.chart_service import (
    build_pdf_bytes,
    build_word_bytes,
    get_assignee_rank,
    get_report_detail,
    get_risk_dist,
    get_trend_data,
    get_type_dist,
    list_report_history,
)

router = APIRouter(prefix="/reports", tags=["reports"])


def _utc_midnight(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _resolve_range(
    date_start: Optional[str],
    date_end: Optional[str],
) -> tuple[datetime, datetime]:
    """将 YYYY-MM-DD 字符串解析为 UTC datetime 区间；未传则默认本周。"""
    today = date.today()
    if date_start and date_end:
        ds = _utc_midnight(date.fromisoformat(date_start))
        de = _utc_midnight(date.fromisoformat(date_end)) + timedelta(days=1)
    else:
        week_monday = today - timedelta(days=today.weekday())
        ds = _utc_midnight(week_monday)
        de = _utc_midnight(today) + timedelta(days=1)
    return ds, de


# ---------------------------------------------------------------------------
# 图表统计接口
# ---------------------------------------------------------------------------

@router.get("/charts/trend", summary="任务趋势图（最近 N 天）")
async def chart_trend(
    days: int = Query(default=14, ge=7, le=90, description="查询天数"),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    result = await get_trend_data(session, days=days)
    return success(result.model_dump())


@router.get("/charts/type", summary="任务类型分布")
async def chart_type(
    date_start: Optional[str] = Query(default=None, description="起始日期 YYYY-MM-DD"),
    date_end: Optional[str] = Query(default=None, description="结束日期 YYYY-MM-DD"),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    ds, de = _resolve_range(date_start, date_end)
    result = await get_type_dist(session, ds, de)
    return success(result.model_dump())


@router.get("/charts/risk", summary="风险分布")
async def chart_risk(
    date_start: Optional[str] = Query(default=None, description="起始日期 YYYY-MM-DD"),
    date_end: Optional[str] = Query(default=None, description="结束日期 YYYY-MM-DD"),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    ds, de = _resolve_range(date_start, date_end)
    result = await get_risk_dist(session, ds, de)
    return success(result.model_dump())


@router.get("/charts/assignee", summary="负责人完成排行")
async def chart_assignee(
    date_start: Optional[str] = Query(default=None, description="起始日期 YYYY-MM-DD"),
    date_end: Optional[str] = Query(default=None, description="结束日期 YYYY-MM-DD"),
    top_n: int = Query(default=10, ge=3, le=20),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    ds, de = _resolve_range(date_start, date_end)
    result = await get_assignee_rank(session, ds, de, top_n=top_n)
    return success(result.model_dump())


# ---------------------------------------------------------------------------
# 历史报告列表 / 详情
# ---------------------------------------------------------------------------

@router.get("/history", summary="历史报告列表")
async def report_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    kind: Optional[str] = Query(default=None, description="daily_summary | weekly_summary"),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    result = await list_report_history(session, page=page, page_size=page_size, kind=kind)
    return success(result.model_dump(mode="json"))


@router.get("/history/{report_id}", summary="报告详情")
async def report_detail(
    report_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    detail = await get_report_detail(session, report_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    return success(detail.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# 文件导出
# ---------------------------------------------------------------------------

@router.get("/export/word/{report_id}", summary="下载 Word 报告")
async def export_word(
    report_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> StreamingResponse:
    detail = await get_report_detail(session, report_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="报告不存在")

    try:
        doc_bytes = build_word_bytes(detail.title, detail.content)
    except ModuleNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="Word 导出依赖未安装，请在 backend 目录执行：pip install python-docx",
        ) from exc
    ascii_fallback = f"report_{report_id}.docx"
    encoded_name = quote(detail.title.replace("/", "-") + ".docx")

    return StreamingResponse(
        iter([doc_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded_name}"},
    )


@router.get("/export/pdf/{report_id}", summary="下载 PDF 报告")
async def export_pdf(
    report_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> StreamingResponse:
    detail = await get_report_detail(session, report_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="报告不存在")

    try:
        pdf_bytes = build_pdf_bytes(detail.title, detail.content)
    except ModuleNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="PDF 导出依赖未安装，请在 backend 目录执行：pip install reportlab",
        ) from exc
    ascii_fallback = f"report_{report_id}.pdf"
    encoded_name = quote(detail.title.replace("/", "-") + ".pdf")

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded_name}"},
    )
