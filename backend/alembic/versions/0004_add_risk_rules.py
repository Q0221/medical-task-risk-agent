"""add risk_rules table with seed data

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_MYSQL_OPTS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

_SEED_RULES = [
    {
        "name": "患者安全关键词",
        "description": "患者直接安全相关高危关键词，命中即为紧急风险",
        "rule_type": "keyword",
        "keywords": '["死亡","感染","输液反应","过敏","坠床","烫伤","窒息","休克","出血","猝死"]',
        "task_types": "[]",
        "baseline_level": "critical",
        "is_active": 1,
    },
    {
        "name": "设备异常关键词",
        "description": "医疗设备故障/异常相关关键词，命中为高风险",
        "rule_type": "keyword",
        "keywords": '["漏液","短路","故障","异响","过热","断电","警报","误报","精度偏差"]',
        "task_types": '["device_anomaly"]',
        "baseline_level": "high",
        "is_active": 1,
    },
    {
        "name": "紧急程度关键词",
        "description": "表达紧迫性的关键词，命中提升为高风险",
        "rule_type": "keyword",
        "keywords": '["紧急","立即","严重","危急","致命","恶化","突发"]',
        "task_types": "[]",
        "baseline_level": "high",
        "is_active": 1,
    },
    {
        "name": "合规违规关键词",
        "description": "合规/监管相关敏感词，命中为中风险",
        "rule_type": "keyword",
        "keywords": '["违规","违法","举报","投诉","处罚","责令整改","警告"]',
        "task_types": '["compliance_review"]',
        "baseline_level": "medium",
        "is_active": 1,
    },
    {
        "name": "不良事件类型基线",
        "description": "不良事件任务类型基线风险等级为高风险",
        "rule_type": "type_baseline",
        "keywords": "[]",
        "task_types": '["adverse_event"]',
        "baseline_level": "high",
        "is_active": 1,
    },
    {
        "name": "设备异常类型基线",
        "description": "设备异常任务类型基线风险等级为高风险",
        "rule_type": "type_baseline",
        "keywords": "[]",
        "task_types": '["device_anomaly"]',
        "baseline_level": "high",
        "is_active": 1,
    },
    {
        "name": "投诉处理类型基线",
        "description": "投诉处理任务类型基线风险等级为中风险",
        "rule_type": "type_baseline",
        "keywords": "[]",
        "task_types": '["complaint"]',
        "baseline_level": "medium",
        "is_active": 1,
    },
    {
        "name": "合规审核类型基线",
        "description": "合规审核任务类型基线风险等级为中风险",
        "rule_type": "type_baseline",
        "keywords": "[]",
        "task_types": '["compliance_review"]',
        "baseline_level": "medium",
        "is_active": 1,
    },
    {
        "name": "产品缺陷关键词",
        "description": "产品质量/缺陷相关关键词，命中为中风险",
        "rule_type": "keyword",
        "keywords": '["缺陷","召回","质量问题","批次问题","不合格","漏洞","断裂"]',
        "task_types": '["product_feedback"]',
        "baseline_level": "medium",
        "is_active": 1,
    },
    {
        "name": "数据安全关键词",
        "description": "患者隐私/数据安全相关关键词，命中为高风险",
        "rule_type": "keyword",
        "keywords": '["隐私泄露","数据泄漏","未经授权","权限越级","病历外泄"]',
        "task_types": "[]",
        "baseline_level": "high",
        "is_active": 1,
    },
]


def upgrade() -> None:
    op.create_table(
        "risk_rules",
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
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("rule_type", sa.String(32), nullable=False, server_default="keyword"),
        sa.Column("keywords", sa.JSON, nullable=True),
        sa.Column("task_types", sa.JSON, nullable=True),
        sa.Column("baseline_level", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
        **_MYSQL_OPTS,
    )
    op.create_index("ix_risk_rules_name", "risk_rules", ["name"])
    op.create_index("ix_risk_rules_rule_type", "risk_rules", ["rule_type"])
    op.create_index("ix_risk_rules_is_active", "risk_rules", ["is_active"])

    # 写入初始规则
    conn = op.get_bind()
    for rule in _SEED_RULES:
        conn.execute(
            sa.text(
                "INSERT INTO risk_rules (name, description, rule_type, keywords, task_types, baseline_level, is_active) "
                "VALUES (:name, :description, :rule_type, :keywords, :task_types, :baseline_level, :is_active)"
            ),
            rule,
        )


def downgrade() -> None:
    op.drop_index("ix_risk_rules_is_active", table_name="risk_rules")
    op.drop_index("ix_risk_rules_rule_type", table_name="risk_rules")
    op.drop_index("ix_risk_rules_name", table_name="risk_rules")
    op.drop_table("risk_rules")
