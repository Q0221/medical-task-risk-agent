"""init schema: 11 base tables.

Revision ID: 0001
Revises:
Create Date: 2026-06-02

包含表：
    roles, users, user_roles,
    hospitals, products,
    tasks, task_events,
    risk_records, knowledge_gap_tasks,
    notifications, agent_traces
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_MYSQL_OPTS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
}


def _common_cols() -> list:
    """所有业务表都带的通用列：id / created_at / updated_at / deleted_at。"""
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "roles",
        *_common_cols(),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        **_MYSQL_OPTS,
    )
    op.create_index("ix_roles_created_at", "roles", ["created_at"])
    op.create_index("ix_roles_deleted_at", "roles", ["deleted_at"])

    op.create_table(
        "users",
        *_common_cols(),
        sa.Column("employee_no", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("email", sa.String(128), nullable=True, unique=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("wxwork_userid", sa.String(64), nullable=True, unique=True),
        sa.Column("department", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        **_MYSQL_OPTS,
    )
    op.create_index("ix_users_department", "users", ["department"])
    op.create_index("ix_users_created_at", "users", ["created_at"])
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"])

    op.create_table(
        "user_roles",
        *_common_cols(),
        sa.Column("user_id", sa.BigInteger, nullable=False),
        sa.Column("role_id", sa.BigInteger, nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_role"),
        **_MYSQL_OPTS,
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])

    op.create_table(
        "hospitals",
        *_common_cols(),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("level", sa.String(16), nullable=True),
        sa.Column("region", sa.String(64), nullable=True),
        sa.Column("risk_score", sa.Integer, nullable=False, server_default="0"),
        sa.Column("contact_name", sa.String(64), nullable=True),
        sa.Column("contact_phone", sa.String(32), nullable=True),
        **_MYSQL_OPTS,
    )
    op.create_index("ix_hospitals_name", "hospitals", ["name"])
    op.create_index("ix_hospitals_region", "hospitals", ["region"])

    op.create_table(
        "products",
        *_common_cols(),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("business_unit", sa.String(64), nullable=True),
        sa.Column("description", sa.String(255), nullable=True),
        **_MYSQL_OPTS,
    )
    op.create_index("ix_products_name", "products", ["name"])
    op.create_index("ix_products_category", "products", ["category"])

    op.create_table(
        "tasks",
        *_common_cols(),
        sa.Column("type", sa.String(32), nullable=False, server_default="other"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="agent"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("priority", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("assignee_id", sa.BigInteger, nullable=False),
        sa.Column("collaborators", mysql.JSON, nullable=True),
        sa.Column("created_by", sa.BigInteger, nullable=False),
        sa.Column("hospital_id", sa.BigInteger, nullable=True),
        sa.Column("product_id", sa.BigInteger, nullable=True),
        sa.Column(
            "business_object_type",
            sa.String(32),
            nullable=False,
            server_default="none",
        ),
        sa.Column("business_object_id", sa.String(64), nullable=True),
        sa.Column("remind_at", sa.DateTime, nullable=True),
        sa.Column("due_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="low"),
        sa.Column("risk_reason", sa.Text, nullable=True),
        sa.Column("risk_suggested_action", sa.Text, nullable=True),
        sa.Column("review_status", sa.String(16), nullable=False, server_default="none"),
        sa.Column("reviewer_id", sa.BigInteger, nullable=True),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column("review_comment", sa.Text, nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("agent_session_id", sa.String(64), nullable=True),
        sa.Column("extra", mysql.JSON, nullable=True),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="SET NULL"),
        **_MYSQL_OPTS,
    )
    op.create_index("ix_tasks_type", "tasks", ["type"])
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_priority", "tasks", ["priority"])
    op.create_index("ix_tasks_assignee_id", "tasks", ["assignee_id"])
    op.create_index("ix_tasks_hospital_id", "tasks", ["hospital_id"])
    op.create_index("ix_tasks_product_id", "tasks", ["product_id"])
    op.create_index("ix_tasks_remind_at", "tasks", ["remind_at"])
    op.create_index("ix_tasks_due_at", "tasks", ["due_at"])
    op.create_index("ix_tasks_risk_level", "tasks", ["risk_level"])
    op.create_index("ix_tasks_review_status", "tasks", ["review_status"])
    op.create_index("ix_tasks_trace_id", "tasks", ["trace_id"])
    op.create_index("ix_tasks_created_at", "tasks", ["created_at"])
    op.create_index("ix_tasks_deleted_at", "tasks", ["deleted_at"])
    op.create_index("ix_tasks_assignee_status", "tasks", ["assignee_id", "status"])
    op.create_index("ix_tasks_remind_at_status", "tasks", ["remind_at", "status"])
    op.create_index("ix_tasks_due_at_status", "tasks", ["due_at", "status"])
    op.create_index(
        "ix_tasks_business_object",
        "tasks",
        ["business_object_type", "business_object_id"],
    )

    op.create_table(
        "task_events",
        *_common_cols(),
        sa.Column("task_id", sa.BigInteger, nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("operator_id", sa.BigInteger, nullable=True),
        sa.Column("operator_kind", sa.String(16), nullable=False, server_default="user"),
        sa.Column("payload", mysql.JSON, nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["operator_id"], ["users.id"], ondelete="SET NULL"),
        **_MYSQL_OPTS,
    )
    op.create_index("ix_task_events_task_id", "task_events", ["task_id"])
    op.create_index("ix_task_events_event_type", "task_events", ["event_type"])
    op.create_index("ix_task_events_trace_id", "task_events", ["trace_id"])

    op.create_table(
        "risk_records",
        *_common_cols(),
        sa.Column("task_id", sa.BigInteger, nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="low"),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("suggested_action", sa.Text, nullable=True),
        sa.Column("keywords_hit", mysql.JSON, nullable=True),
        sa.Column("rule_hit", mysql.JSON, nullable=True),
        sa.Column("llm_judgement", mysql.JSON, nullable=True),
        sa.Column(
            "review_status", sa.String(16), nullable=False, server_default="pending"
        ),
        sa.Column("reviewer_id", sa.BigInteger, nullable=True),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column("review_comment", sa.Text, nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="SET NULL"),
        **_MYSQL_OPTS,
    )
    op.create_index("ix_risk_records_task_id", "risk_records", ["task_id"])
    op.create_index("ix_risk_records_risk_level", "risk_records", ["risk_level"])
    op.create_index("ix_risk_records_review_status", "risk_records", ["review_status"])
    op.create_index("ix_risk_records_trace_id", "risk_records", ["trace_id"])

    op.create_table(
        "knowledge_gap_tasks",
        *_common_cols(),
        sa.Column("source_task_id", sa.BigInteger, nullable=True),
        sa.Column("original_question", sa.Text, nullable=False),
        sa.Column("retrieval_query", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("rag_hits_snapshot", mysql.JSON, nullable=True),
        sa.Column("assignee_id", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("resolution_note", sa.Text, nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["source_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], ondelete="RESTRICT"),
        **_MYSQL_OPTS,
    )
    op.create_index(
        "ix_knowledge_gap_tasks_source_task_id",
        "knowledge_gap_tasks",
        ["source_task_id"],
    )
    op.create_index(
        "ix_knowledge_gap_tasks_assignee_id", "knowledge_gap_tasks", ["assignee_id"]
    )
    op.create_index("ix_knowledge_gap_tasks_status", "knowledge_gap_tasks", ["status"])
    op.create_index(
        "ix_knowledge_gap_tasks_trace_id", "knowledge_gap_tasks", ["trace_id"]
    )

    op.create_table(
        "notifications",
        *_common_cols(),
        sa.Column("task_id", sa.BigInteger, nullable=True),
        sa.Column("kind", sa.String(32), nullable=False, server_default="task_created"),
        sa.Column("channel", sa.String(16), nullable=False, server_default="wxwork"),
        sa.Column("recipient_user_id", sa.BigInteger, nullable=True),
        sa.Column("recipient_address", sa.String(255), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("payload", mysql.JSON, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sent_at", sa.DateTime, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        **_MYSQL_OPTS,
    )
    op.create_index("ix_notifications_task_id", "notifications", ["task_id"])
    op.create_index("ix_notifications_kind", "notifications", ["kind"])
    op.create_index("ix_notifications_channel", "notifications", ["channel"])
    op.create_index("ix_notifications_status", "notifications", ["status"])
    op.create_index("ix_notifications_trace_id", "notifications", ["trace_id"])

    op.create_table(
        "agent_traces",
        *_common_cols(),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("parent_id", sa.BigInteger, nullable=True),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("node", sa.String(32), nullable=False, server_default="supervisor"),
        sa.Column("status", sa.String(16), nullable=False, server_default="ok"),
        sa.Column("input_data", mysql.JSON, nullable=True),
        sa.Column("output_data", mysql.JSON, nullable=True),
        sa.Column("tool_name", sa.String(64), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["agent_traces.id"], ondelete="SET NULL"
        ),
        **_MYSQL_OPTS,
    )
    op.create_index("ix_agent_traces_trace_id", "agent_traces", ["trace_id"])
    op.create_index("ix_agent_traces_session_id", "agent_traces", ["session_id"])
    op.create_index("ix_agent_traces_node", "agent_traces", ["node"])
    op.create_index("ix_agent_traces_status", "agent_traces", ["status"])
    op.create_index("ix_agent_traces_trace_node", "agent_traces", ["trace_id", "node"])


def downgrade() -> None:
    op.drop_table("agent_traces")
    op.drop_table("notifications")
    op.drop_table("knowledge_gap_tasks")
    op.drop_table("risk_records")
    op.drop_table("task_events")
    op.drop_table("tasks")
    op.drop_table("products")
    op.drop_table("hospitals")
    op.drop_table("user_roles")
    op.drop_table("users")
    op.drop_table("roles")
