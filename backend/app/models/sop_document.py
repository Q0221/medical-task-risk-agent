"""SOP 文档主数据表。

支持多版本管理：同一 code 可有多条记录，通过 status 区分当前版本（active）
和历史版本（archived）。每次发布新版本时将旧版本置为 archived，新版本置为 active。
"""

from typing import Optional

from sqlalchemy import JSON, BigInteger, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class SopDocument(BaseModel):
    __tablename__ = "sop_documents"

    code: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True, comment="SOP 编号，如 SOP-ADV-001"
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True, comment="SOP 类别，如 设备异常/投诉处理"
    )
    department: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="维护部门"
    )
    version: Mapped[str] = mapped_column(
        String(16), nullable=False, default="v1.0", comment="版本号，如 v1.0 / v2.3"
    )
    tags: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="标签列表，如 ['报警','患者安全']"
    )
    content: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="文档全文内容"
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="active",
        index=True,
        comment="active=当前版本 / draft=草稿 / archived=历史版本",
    )
    hit_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="近 30 天检索命中次数"
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="创建人 user_id",
    )
    parent_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("sop_documents.id", ondelete="SET NULL"),
        nullable=True,
        comment="上一版本 ID（版本链）",
    )
