"""add sop_documents table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MYSQL_OPTS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
}


def upgrade() -> None:
    op.create_table(
        "sop_documents",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(32), nullable=False, comment="SOP 编号"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("category", sa.String(64), nullable=True, comment="SOP 类别"),
        sa.Column("department", sa.String(64), nullable=True, comment="维护部门"),
        sa.Column("version", sa.String(16), nullable=False, server_default="v1.0"),
        sa.Column("tags", sa.JSON(), nullable=True, comment="标签列表"),
        sa.Column("content", sa.Text(), nullable=True, comment="文档全文"),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="active",
            comment="active/draft/archived",
        ),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "parent_id",
            sa.BigInteger(),
            sa.ForeignKey("sop_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        **_MYSQL_OPTS,
    )
    op.create_index("ix_sop_documents_code", "sop_documents", ["code"])
    op.create_index("ix_sop_documents_title", "sop_documents", ["title"])
    op.create_index("ix_sop_documents_category", "sop_documents", ["category"])
    op.create_index("ix_sop_documents_status", "sop_documents", ["status"])
    op.create_index("ix_sop_documents_created_at", "sop_documents", ["created_at"])
    op.create_index("ix_sop_documents_deleted_at", "sop_documents", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_sop_documents_deleted_at", table_name="sop_documents")
    op.drop_index("ix_sop_documents_created_at", table_name="sop_documents")
    op.drop_index("ix_sop_documents_status", table_name="sop_documents")
    op.drop_index("ix_sop_documents_category", table_name="sop_documents")
    op.drop_index("ix_sop_documents_title", table_name="sop_documents")
    op.drop_index("ix_sop_documents_code", table_name="sop_documents")
    op.drop_table("sop_documents")
