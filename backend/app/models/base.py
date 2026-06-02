"""SQLAlchemy 声明式基类与通用 Mixin。

约定：
- 所有业务表主键：BigInteger 自增。
- 所有业务表必带：created_at / updated_at / deleted_at（软删除）。
- 通过 BaseModel 抽象类一次性继承上述能力。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有 ORM 模型的最底层基类。"""


class TimestampMixin:
    """创建时间 / 更新时间字段。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SoftDeleteMixin:
    """软删除：deleted_at IS NULL 视为有效记录。"""

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        default=None,
        index=True,
    )


class BaseModel(Base, TimestampMixin, SoftDeleteMixin):
    """业务表统一基类：BigInt 自增主键 + 时间戳 + 软删除。

    子类只需声明 __tablename__ 与业务字段。
    """

    __abstract__ = True

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
