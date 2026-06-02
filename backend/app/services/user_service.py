"""员工查询服务：按姓名 / 工号查找，提供默认用户兜底。"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizException
from app.models.enums import RoleCode
from app.models.user import Role, User, UserRole


async def get_user_by_id(session: AsyncSession, user_id: int) -> Optional[User]:
    return (
        await session.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
    ).scalar_one_or_none()


async def find_user_by_name(session: AsyncSession, name: str) -> Optional[User]:
    """先精确匹配；找不到再 LIKE 模糊匹配（前缀）。"""
    name = name.strip()
    if not name:
        return None

    exact = (
        await session.execute(
            select(User).where(User.name == name, User.deleted_at.is_(None)).limit(1)
        )
    ).scalar_one_or_none()
    if exact:
        return exact

    return (
        await session.execute(
            select(User)
            .where(User.name.like(f"%{name}%"), User.deleted_at.is_(None))
            .limit(1)
        )
    ).scalar_one_or_none()


async def get_default_user(session: AsyncSession) -> User:
    """获取默认用户：优先 admin 角色第一个；否则全表第一个有效用户。"""
    admin = (
        await session.execute(
            select(User)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                Role.code == RoleCode.ADMIN.value,
                User.deleted_at.is_(None),
                Role.deleted_at.is_(None),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if admin:
        return admin

    fallback = (
        await session.execute(
            select(User).where(User.deleted_at.is_(None)).order_by(User.id).limit(1)
        )
    ).scalar_one_or_none()
    if fallback is None:
        raise BizException(
            code=5040,
            message="数据库无任何用户，请先执行 `python -m scripts.seed`",
        )
    return fallback
