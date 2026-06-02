"""员工与角色。

users：员工主数据，登录身份；
roles：内置角色（客服 / 医学 / 产品 / 质控 / 合规 / 主管 / 管理员）；
user_roles：员工-角色多对多。
"""

from typing import List, Optional

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Role(BaseModel):
    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, comment="角色码")
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="角色名")
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    users: Mapped[List["User"]] = relationship(
        secondary="user_roles", back_populates="roles", lazy="selectin"
    )


class User(BaseModel):
    __tablename__ = "users"

    employee_no: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, comment="工号"
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="姓名")
    email: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, unique=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    wxwork_userid: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, unique=True, comment="企业微信 userid"
    )
    department: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    roles: Mapped[List[Role]] = relationship(
        secondary="user_roles", back_populates="users", lazy="selectin"
    )


class UserRole(BaseModel):
    """员工-角色关联表（多对多）。"""

    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
