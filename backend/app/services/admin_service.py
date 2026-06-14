"""系统管理服务层。

职责：
- 通知渠道配置查询 / 更新 / 测试连通性
- 业务字典 CRUD
- 人员权限查询 / 角色变更 / 启停账号
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizException
from app.core.logger import get_logger
from app.models.system_config import SystemConfig
from app.models.user import Role, User, UserRole
from app.schemas.admin import (
    AdminUserUpdateRequest,
    DictItemCreateRequest,
    DictItemUpdateRequest,
    NotifyChannelUpdateRequest,
)

logger = get_logger(__name__)

_CAT_CHANNEL = "notify_channel"
_CAT_DICT = "dictionary"


# ---------------------------------------------------------------------------
# 通知渠道配置
# ---------------------------------------------------------------------------

async def list_notify_channels(session: AsyncSession) -> Sequence[SystemConfig]:
    items = (
        await session.execute(
            select(SystemConfig)
            .where(
                SystemConfig.category == _CAT_CHANNEL,
                SystemConfig.deleted_at.is_(None),
            )
            .order_by(SystemConfig.sort_order.asc())
        )
    ).scalars().all()
    return items


async def update_notify_channel(
    session: AsyncSession,
    config_key: str,
    req: NotifyChannelUpdateRequest,
) -> SystemConfig:
    cfg = await _get_config(session, _CAT_CHANNEL, config_key)
    if cfg is None:
        raise BizException(code=4044, message=f"通知渠道 {config_key} 不存在")

    cfg.config_value = req.config_value
    if req.is_active is not None:
        cfg.is_active = req.is_active

    await session.flush()
    await session.refresh(cfg)
    logger.info("notify_channel updated: key=%s", config_key)
    return cfg


async def test_notify_channel(config_key: str, config_value: dict) -> dict:
    """简单检查渠道配置完整性（不做真实网络请求）。"""
    if config_key == "im":
        return {"success": True, "message": "站内消息渠道始终可用"}

    if config_key == "wxwork":
        webhook_url = config_value.get("webhook_url", "")
        if not webhook_url or not webhook_url.startswith("https://"):
            return {"success": False, "message": "Webhook URL 未填写或格式不正确"}
        return {"success": True, "message": "企业微信 Webhook 配置格式正确，连通性需在实际发送时验证"}

    if config_key == "email":
        host = config_value.get("smtp_host", "")
        user = config_value.get("smtp_user", "")
        from_addr = config_value.get("smtp_from", "")
        missing = []
        if not host:
            missing.append("SMTP 主机")
        if not user:
            missing.append("SMTP 用户名")
        if not from_addr:
            missing.append("发件人地址")
        if missing:
            return {"success": False, "message": f"以下字段未填写：{', '.join(missing)}"}
        return {"success": True, "message": f"邮件渠道配置格式正确（{host}:{config_value.get('smtp_port', 465)}）"}

    return {"success": False, "message": f"未知渠道 {config_key}"}


# ---------------------------------------------------------------------------
# 业务字典
# ---------------------------------------------------------------------------

async def list_dict_items(
    session: AsyncSession,
    include_inactive: bool = True,
) -> tuple[Sequence[SystemConfig], int]:
    base = select(SystemConfig).where(
        SystemConfig.category == _CAT_DICT,
        SystemConfig.deleted_at.is_(None),
    )
    if not include_inactive:
        base = base.where(SystemConfig.is_active.is_(True))

    items = (
        await session.execute(base.order_by(SystemConfig.sort_order.asc()))
    ).scalars().all()
    return items, len(items)


async def get_dict_item(session: AsyncSession, item_id: int) -> Optional[SystemConfig]:
    return (
        await session.execute(
            select(SystemConfig).where(
                SystemConfig.id == item_id,
                SystemConfig.category == _CAT_DICT,
                SystemConfig.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def create_dict_item(
    session: AsyncSession,
    req: DictItemCreateRequest,
) -> SystemConfig:
    existing = await _get_config(session, _CAT_DICT, req.config_key)
    if existing is not None:
        raise BizException(code=4090, message=f"字典键 {req.config_key} 已存在")

    item = SystemConfig(
        category=_CAT_DICT,
        config_key=req.config_key,
        label=req.label,
        description=req.description,
        config_value=req.config_value,
        is_active=True,
        sort_order=req.sort_order,
    )
    session.add(item)
    await session.flush()
    await session.refresh(item)
    logger.info("dict_item created: key=%s", req.config_key)
    return item


async def update_dict_item(
    session: AsyncSession,
    item_id: int,
    req: DictItemUpdateRequest,
) -> SystemConfig:
    item = await get_dict_item(session, item_id)
    if item is None:
        raise BizException(code=4044, message=f"字典项 id={item_id} 不存在")

    if req.label is not None:
        item.label = req.label
    if req.description is not None:
        item.description = req.description
    if req.config_value is not None:
        item.config_value = req.config_value
    if req.is_active is not None:
        item.is_active = req.is_active
    if req.sort_order is not None:
        item.sort_order = req.sort_order

    await session.flush()
    await session.refresh(item)
    return item


async def delete_dict_item(session: AsyncSession, item_id: int) -> None:
    item = await get_dict_item(session, item_id)
    if item is None:
        raise BizException(code=4044, message=f"字典项 id={item_id} 不存在")
    item.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await session.flush()
    logger.info("dict_item deleted: id=%s", item_id)


# ---------------------------------------------------------------------------
# 人员权限
# ---------------------------------------------------------------------------

async def list_users(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    department: Optional[str] = None,
) -> tuple[Sequence[User], int]:
    page = max(1, page)
    page_size = max(1, min(100, page_size))

    base = select(User).where(User.deleted_at.is_(None))
    count_q = select(func.count()).select_from(User).where(User.deleted_at.is_(None))

    if search:
        like = f"%{search}%"
        base = base.where(
            User.name.ilike(like) | User.employee_no.ilike(like) | User.email.ilike(like)
        )
        count_q = count_q.where(
            User.name.ilike(like) | User.employee_no.ilike(like) | User.email.ilike(like)
        )
    if department:
        base = base.where(User.department == department)
        count_q = count_q.where(User.department == department)

    items = (
        await session.execute(
            base.order_by(User.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    total = (await session.execute(count_q)).scalar_one()
    return items, int(total)


async def get_user(session: AsyncSession, user_id: int) -> Optional[User]:
    return (
        await session.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
    ).scalar_one_or_none()


async def update_user(
    session: AsyncSession,
    user_id: int,
    req: AdminUserUpdateRequest,
) -> User:
    user = await get_user(session, user_id)
    if user is None:
        raise BizException(code=4044, message=f"用户 id={user_id} 不存在")

    if req.is_active is not None:
        user.is_active = req.is_active
    if req.department is not None:
        user.department = req.department

    if req.role_codes is not None:
        await _replace_user_roles(session, user_id, req.role_codes)

    await session.flush()
    await session.refresh(user)
    logger.info("admin updated user: id=%s", user_id)
    return user


async def _replace_user_roles(
    session: AsyncSession,
    user_id: int,
    role_codes: list[str],
) -> None:
    """删除用户现有角色，按 role_codes 重新绑定。"""
    existing = (
        await session.execute(
            select(UserRole).where(UserRole.user_id == user_id)
        )
    ).scalars().all()
    for ur in existing:
        await session.delete(ur)
    await session.flush()

    if not role_codes:
        return

    roles = (
        await session.execute(
            select(Role).where(Role.code.in_(role_codes), Role.deleted_at.is_(None))
        )
    ).scalars().all()
    for role in roles:
        session.add(UserRole(user_id=user_id, role_id=role.id))
    await session.flush()


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

async def _get_config(
    session: AsyncSession, category: str, config_key: str
) -> Optional[SystemConfig]:
    return (
        await session.execute(
            select(SystemConfig).where(
                SystemConfig.category == category,
                SystemConfig.config_key == config_key,
                SystemConfig.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
