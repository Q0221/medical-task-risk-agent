"""系统管理接口。

已实现：
- GET    /admin/notify-channels                    通知渠道配置列表
- PATCH  /admin/notify-channels/{key}              更新渠道配置
- POST   /admin/notify-channels/{key}/test         测试渠道连通性
- GET    /admin/dict-items                         业务字典列表
- POST   /admin/dict-items                         新增字典项
- PATCH  /admin/dict-items/{item_id}               更新字典项
- DELETE /admin/dict-items/{item_id}               删除字典项
- GET    /admin/users                              人员列表（含角色）
- PATCH  /admin/users/{user_id}                   更新人员（启停/角色/部门）
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_app_roles
from app.core.response import success
from app.schemas.admin import (
    AdminUserListResponse,
    AdminUserOut,
    AdminUserUpdateRequest,
    DictItemCreateRequest,
    DictItemListResponse,
    DictItemOut,
    DictItemUpdateRequest,
    NotifyChannelOut,
    NotifyChannelTestResult,
    NotifyChannelUpdateRequest,
)
from app.services import admin_service
from app.services.auth_service import CurrentUser

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# 通知渠道配置
# ---------------------------------------------------------------------------

@router.get("/notify-channels", summary="通知渠道配置列表")
async def list_notify_channels(
    current_user: CurrentUser = Depends(require_app_roles("admin")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    items = await admin_service.list_notify_channels(session)
    return success([NotifyChannelOut.model_validate(c).model_dump(mode="json") for c in items])


@router.patch("/notify-channels/{config_key}", summary="更新通知渠道配置")
async def update_notify_channel(
    config_key: str = Path(...),
    body: NotifyChannelUpdateRequest = ...,
    current_user: CurrentUser = Depends(require_app_roles("admin")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    async with session.begin():
        cfg = await admin_service.update_notify_channel(session, config_key, body)
    return success(NotifyChannelOut.model_validate(cfg).model_dump(mode="json"))


@router.post("/notify-channels/{config_key}/test", summary="测试通知渠道配置")
async def test_notify_channel(
    config_key: str = Path(...),
    body: NotifyChannelUpdateRequest = ...,
    current_user: CurrentUser = Depends(require_app_roles("admin")),
) -> dict:
    result = await admin_service.test_notify_channel(config_key, body.config_value)
    return success(NotifyChannelTestResult(**result).model_dump(mode="json"))


# ---------------------------------------------------------------------------
# 业务字典
# ---------------------------------------------------------------------------

@router.get("/dict-items", summary="业务字典列表")
async def list_dict_items(
    include_inactive: bool = Query(default=True),
    current_user: CurrentUser = Depends(require_app_roles("admin")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    items, total = await admin_service.list_dict_items(
        session, include_inactive=include_inactive
    )
    resp = DictItemListResponse(
        items=[DictItemOut.model_validate(i) for i in items],
        total=total,
    )
    return success(resp.model_dump(mode="json"))


@router.post("/dict-items", summary="新增业务字典项")
async def create_dict_item(
    body: DictItemCreateRequest,
    current_user: CurrentUser = Depends(require_app_roles("admin")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    async with session.begin():
        item = await admin_service.create_dict_item(session, body)
    return success(DictItemOut.model_validate(item).model_dump(mode="json"))


@router.patch("/dict-items/{item_id}", summary="更新业务字典项")
async def update_dict_item(
    item_id: int = Path(..., ge=1),
    body: DictItemUpdateRequest = ...,
    current_user: CurrentUser = Depends(require_app_roles("admin")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    async with session.begin():
        item = await admin_service.update_dict_item(session, item_id, body)
    return success(DictItemOut.model_validate(item).model_dump(mode="json"))


@router.delete("/dict-items/{item_id}", summary="删除业务字典项")
async def delete_dict_item(
    item_id: int = Path(..., ge=1),
    current_user: CurrentUser = Depends(require_app_roles("admin")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    async with session.begin():
        await admin_service.delete_dict_item(session, item_id)
    return success({"item_id": item_id, "message": "字典项已删除"})


# ---------------------------------------------------------------------------
# 人员权限
# ---------------------------------------------------------------------------

@router.get("/users", summary="人员列表（含角色）")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(default=None, description="姓名/工号/邮箱模糊搜索"),
    department: Optional[str] = Query(default=None),
    current_user: CurrentUser = Depends(require_app_roles("admin")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    users, total = await admin_service.list_users(
        session, page=page, page_size=page_size, search=search, department=department
    )

    items = []
    for user in users:
        role_codes = [r.code for r in (user.roles or [])]
        role_names = [r.name for r in (user.roles or [])]
        items.append(AdminUserOut(
            id=user.id,
            employee_no=user.employee_no,
            name=user.name,
            email=user.email,
            phone=user.phone,
            department=user.department,
            wxwork_userid=user.wxwork_userid,
            is_active=user.is_active,
            roles=role_codes,
            role_names=role_names,
            created_at=user.created_at,
        ))

    resp = AdminUserListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
    return success(resp.model_dump(mode="json"))


@router.patch("/users/{user_id}", summary="更新人员信息（启停/角色/部门）")
async def update_user(
    user_id: int = Path(..., ge=1),
    body: AdminUserUpdateRequest = ...,
    current_user: CurrentUser = Depends(require_app_roles("admin")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    async with session.begin():
        user = await admin_service.update_user(session, user_id, body)
    role_codes = [r.code for r in (user.roles or [])]
    role_names = [r.name for r in (user.roles or [])]
    return success(AdminUserOut(
        id=user.id,
        employee_no=user.employee_no,
        name=user.name,
        email=user.email,
        phone=user.phone,
        department=user.department,
        wxwork_userid=user.wxwork_userid,
        is_active=user.is_active,
        roles=role_codes,
        role_names=role_names,
        created_at=user.created_at,
    ).model_dump(mode="json"))
