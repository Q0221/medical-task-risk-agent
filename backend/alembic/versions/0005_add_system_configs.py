"""add system_configs table with seed data

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-12
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_MYSQL_OPTS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

# ---------------------------------------------------------------------------
# 通知渠道初始配置
# ---------------------------------------------------------------------------
_NOTIFY_CHANNELS = [
    {
        "category": "notify_channel",
        "config_key": "im",
        "label": "站内消息",
        "description": "系统内置消息通知，无需额外配置，始终可用。",
        "config_value": json.dumps({"is_enabled": True}),
        "is_active": 1,
        "sort_order": 0,
    },
    {
        "category": "notify_channel",
        "config_key": "wxwork",
        "label": "企业微信机器人",
        "description": "通过企业微信群机器人 Webhook 发送通知，填写 Webhook URL 后启用。",
        "config_value": json.dumps({"webhook_url": "", "mention_all": False, "is_enabled": False}),
        "is_active": 1,
        "sort_order": 1,
    },
    {
        "category": "notify_channel",
        "config_key": "email",
        "label": "邮件通知（SMTP）",
        "description": "通过 SMTP 发送邮件通知，填写 SMTP 服务器信息后启用。",
        "config_value": json.dumps({
            "smtp_host": "",
            "smtp_port": 465,
            "smtp_user": "",
            "smtp_password": "",
            "smtp_from": "",
            "use_ssl": True,
            "is_enabled": False,
        }),
        "is_active": 1,
        "sort_order": 2,
    },
]

# ---------------------------------------------------------------------------
# 业务字典初始配置
# ---------------------------------------------------------------------------
_DICT_ITEMS = [
    {
        "category": "dictionary",
        "config_key": "risk_review_timeout_hours",
        "label": "风险审核超时时间（小时）",
        "description": "超过此时长未处理的待审核风险事项将触发自动升级提醒。",
        "config_value": json.dumps({"value": 48}),
        "is_active": 1,
        "sort_order": 0,
    },
    {
        "category": "dictionary",
        "config_key": "urgent_task_threshold_hours",
        "label": "紧急任务处理期限（小时）",
        "description": "优先级为紧急的任务，超过此时长未完成将触发逾期通知。",
        "config_value": json.dumps({"value": 24}),
        "is_active": 1,
        "sort_order": 1,
    },
    {
        "category": "dictionary",
        "config_key": "overdue_check_interval_min",
        "label": "逾期检查间隔（分钟）",
        "description": "后台调度器检查逾期任务的频率。",
        "config_value": json.dumps({"value": 30}),
        "is_active": 1,
        "sort_order": 2,
    },
    {
        "category": "dictionary",
        "config_key": "notify_retry_max",
        "label": "通知最大重试次数",
        "description": "通知发送失败后的最大重试次数，超过后进入死信队列。",
        "config_value": json.dumps({"value": 3}),
        "is_active": 1,
        "sort_order": 3,
    },
    {
        "category": "dictionary",
        "config_key": "agent_llm_timeout_seconds",
        "label": "Agent LLM 调用超时（秒）",
        "description": "单次 LLM 调用的最大等待时间，超时后使用规则兜底结果。",
        "config_value": json.dumps({"value": 30}),
        "is_active": 1,
        "sort_order": 4,
    },
    {
        "category": "dictionary",
        "config_key": "report_retention_days",
        "label": "报告保留天数",
        "description": "日报/周报通知在系统中的保留时长，超期后软删除。",
        "config_value": json.dumps({"value": 90}),
        "is_active": 1,
        "sort_order": 5,
    },
    {
        "category": "dictionary",
        "config_key": "task_auto_assign_strategy",
        "label": "任务自动分配策略",
        "description": "Agent 创建任务时的默认分配策略。round_robin=轮询；manager_assign=主管手动分配。",
        "config_value": json.dumps({"value": "round_robin", "options": ["round_robin", "manager_assign"]}),
        "is_active": 1,
        "sort_order": 6,
    },
]


def upgrade() -> None:
    op.create_table(
        "system_configs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("deleted_at", sa.DateTime, nullable=True),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("config_key", sa.String(64), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("config_value", sa.JSON, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("category", "config_key", name="uq_system_config_cat_key"),
        **_MYSQL_OPTS,
    )
    op.create_index("ix_system_configs_category", "system_configs", ["category"])
    op.create_index("ix_system_configs_config_key", "system_configs", ["config_key"])

    conn = op.get_bind()
    insert_sql = sa.text(
        "INSERT INTO system_configs (category, config_key, label, description, config_value, is_active, sort_order) "
        "VALUES (:category, :config_key, :label, :description, :config_value, :is_active, :sort_order)"
    )
    for row in _NOTIFY_CHANNELS + _DICT_ITEMS:
        conn.execute(insert_sql, row)


def downgrade() -> None:
    op.drop_index("ix_system_configs_config_key", table_name="system_configs")
    op.drop_index("ix_system_configs_category", table_name="system_configs")
    op.drop_table("system_configs")
