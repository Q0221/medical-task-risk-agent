"""Demo authentication and role mapping service.

This layer deliberately avoids a database migration. The users and roles are
resolved from the existing seed data, while the password is a shared demo
password configured by AUTH_DEMO_PASSWORD.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import BizException
from app.models.enums import RoleCode
from app.models.user import User


APP_ROLE_LABELS = {
    "employee": "一线员工",
    "manager": "部门主管",
    "operator": "知识运营",
    "admin": "系统管理员",
}

DEMO_ROLE_EMPLOYEE_NO = {
    "employee": "E1001",
    "manager": "E2001",
    "operator": "E1003",
    "admin": "E0001",
}

ACCOUNT_ALIASES = {
    "employee": "E1001",
    "manager": "E2001",
    "operator": "E1003",
    "admin": "E0001",
}

ROLE_CODE_TO_APP_ROLE = {
    RoleCode.ADMIN.value: "admin",
    RoleCode.MANAGER.value: "manager",
    RoleCode.PRODUCT_OPS.value: "operator",
}


@dataclass(frozen=True)
class CurrentUser:
    id: int
    employee_no: str
    name: str
    email: Optional[str]
    department: Optional[str]
    role: str
    role_label: str
    role_codes: set[str]
    is_active: bool


async def authenticate_demo_user(
    session: AsyncSession,
    *,
    username: Optional[str],
    password: str,
    role: Optional[str],
) -> CurrentUser:
    if password != settings.AUTH_DEMO_PASSWORD:
        raise BizException(code=4011, message="账号或密码不正确")

    user = await find_login_user(session, username=username, role=role)
    if user is None:
        raise BizException(code=4011, message="账号或密码不正确")
    current_user = to_current_user(user)
    if not current_user.is_active:
        raise BizException(code=4012, message="账号已停用，请联系管理员")
    return current_user


async def find_login_user(
    session: AsyncSession,
    *,
    username: Optional[str],
    role: Optional[str],
) -> Optional[User]:
    if role:
        employee_no = DEMO_ROLE_EMPLOYEE_NO.get(role)
        if employee_no:
            return await _find_by_employee_no(session, employee_no)

    normalized = (username or "").strip()
    if not normalized:
        return None
    alias = ACCOUNT_ALIASES.get(normalized.lower())
    if alias:
        return await _find_by_employee_no(session, alias)

    return (
        await session.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(
                User.deleted_at.is_(None),
                or_(
                    User.employee_no == normalized,
                    User.email == normalized,
                    User.name == normalized,
                ),
            )
            .limit(1)
        )
    ).scalar_one_or_none()


async def get_current_user_by_id(session: AsyncSession, user_id: int) -> Optional[CurrentUser]:
    user = (
        await session.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.id == user_id, User.deleted_at.is_(None))
            .limit(1)
        )
    ).scalar_one_or_none()
    return to_current_user(user) if user else None


def to_current_user(user: User) -> CurrentUser:
    role_codes = {role.code for role in (user.roles or []) if not role.deleted_at}
    app_role = app_role_from_codes(role_codes)
    return CurrentUser(
        id=user.id,
        employee_no=user.employee_no,
        name=user.name,
        email=user.email,
        department=user.department,
        role=app_role,
        role_label=APP_ROLE_LABELS[app_role],
        role_codes=role_codes,
        is_active=user.is_active,
    )


def app_role_from_codes(role_codes: set[str]) -> str:
    if RoleCode.ADMIN.value in role_codes:
        return "admin"
    if RoleCode.MANAGER.value in role_codes:
        return "manager"
    if RoleCode.PRODUCT_OPS.value in role_codes:
        return "operator"
    return "employee"


def is_manager_or_admin(user: CurrentUser) -> bool:
    return user.role in {"manager", "admin"}


def is_admin(user: CurrentUser) -> bool:
    return user.role == "admin"


async def _find_by_employee_no(session: AsyncSession, employee_no: str) -> Optional[User]:
    return (
        await session.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.employee_no == employee_no, User.deleted_at.is_(None))
            .limit(1)
        )
    ).scalar_one_or_none()
