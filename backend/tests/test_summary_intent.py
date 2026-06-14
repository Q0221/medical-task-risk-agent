"""智能协同报告意图解析测试。"""

from datetime import date

from app.graph.nodes import _parse_summary_request


TODAY = date(2026, 6, 9)


def test_parse_today_daily_summary() -> None:
    req = _parse_summary_request("生成今日日报", today=TODAY)

    assert req is not None
    assert req["summary_type"] == "daily"
    assert req["date_start"].date() == date(2026, 6, 9)
    assert req["date_end"].date() == date(2026, 6, 10)


def test_parse_yesterday_daily_summary() -> None:
    req = _parse_summary_request("生成昨天日报", today=TODAY)

    assert req is not None
    assert req["summary_type"] == "daily"
    assert req["date_start"].date() == date(2026, 6, 8)
    assert req["date_end"].date() == date(2026, 6, 9)


def test_parse_current_week_summary() -> None:
    req = _parse_summary_request("生成本周周报", today=TODAY)

    assert req is not None
    assert req["summary_type"] == "weekly"
    assert req["date_start"].date() == date(2026, 6, 8)
    assert req["date_end"].date() == date(2026, 6, 15)


def test_parse_last_week_summary() -> None:
    req = _parse_summary_request("生成上周周报", today=TODAY)

    assert req is not None
    assert req["summary_type"] == "weekly"
    assert req["date_start"].date() == date(2026, 6, 1)
    assert req["date_end"].date() == date(2026, 6, 8)


def test_parse_explicit_daily_summary_date() -> None:
    req = _parse_summary_request("生成 2026-06-09 日报", today=TODAY)

    assert req is not None
    assert req["summary_type"] == "daily"
    assert req["date_start"].date() == date(2026, 6, 9)
    assert req["date_end"].date() == date(2026, 6, 10)


def test_parse_chinese_explicit_daily_summary_date() -> None:
    req = _parse_summary_request("生成2026年6月8日日报", today=TODAY)

    assert req is not None
    assert req["summary_type"] == "daily"
    assert req["date_start"].date() == date(2026, 6, 8)
    assert req["date_end"].date() == date(2026, 6, 9)


def test_parse_month_day_daily_summary_date() -> None:
    req = _parse_summary_request("生成6月8日日报", today=TODAY)

    assert req is not None
    assert req["summary_type"] == "daily"
    assert req["date_start"].date() == date(2026, 6, 8)
    assert req["date_end"].date() == date(2026, 6, 9)


def test_parse_slash_and_dot_daily_summary_date() -> None:
    slash = _parse_summary_request("生成2026/06/08日报", today=TODAY)
    dot = _parse_summary_request("生成2026.06.08日报", today=TODAY)

    assert slash is not None
    assert dot is not None
    assert slash["date_start"].date() == date(2026, 6, 8)
    assert dot["date_start"].date() == date(2026, 6, 8)


def test_task_creation_text_is_not_summary_intent() -> None:
    req = _parse_summary_request("请张客服明天下午3点回访医院A试用反馈", today=TODAY)

    assert req is None
