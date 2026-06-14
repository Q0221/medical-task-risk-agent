"""系统管理模块 Pydantic 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# 通知渠道配置
# ---------------------------------------------------------------------------

class NotifyChannelOut(BaseModel):
    """通知渠道配置的对外响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    config_key: str
    label: str
    description: Optional[str]
    config_value: Dict[str, Any]
    is_active: bool
    sort_order: int
    updated_at: datetime


class NotifyChannelUpdateRequest(BaseModel):
    """PATCH /admin/notify-channels/{key}"""

    config_value: Dict[str, Any] = Field(description="渠道完整配置 JSON")
    is_active: Optional[bool] = None


class NotifyChannelTestResult(BaseModel):
    success: bool
    message: str


# ---------------------------------------------------------------------------
# 业务字典
# ---------------------------------------------------------------------------

class DictItemOut(BaseModel):
    """系统字典项对外响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    config_key: str
    label: str
    description: Optional[str]
    config_value: Dict[str, Any]
    is_active: bool
    sort_order: int
    updated_at: datetime


class DictItemCreateRequest(BaseModel):
    config_key: str = Field(..., min_length=1, max_length=64)
    label: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = None
    config_value: Dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0


class DictItemUpdateRequest(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = None
    config_value: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class DictItemListResponse(BaseModel):
    items: List[DictItemOut]
    total: int


# ---------------------------------------------------------------------------
# 人员权限
# ---------------------------------------------------------------------------

class AdminUserOut(BaseModel):
    """管理员视角的用户信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_no: str
    name: str
    email: Optional[str]
    phone: Optional[str]
    department: Optional[str]
    wxwork_userid: Optional[str]
    is_active: bool
    roles: List[str] = Field(description="角色码列表")
    role_names: List[str] = Field(description="角色名称列表")
    created_at: datetime


class AdminUserListResponse(BaseModel):
    items: List[AdminUserOut]
    total: int
    page: int
    page_size: int


class AdminUserUpdateRequest(BaseModel):
    """PATCH /admin/users/{id}"""

    is_active: Optional[bool] = None
    role_codes: Optional[List[str]] = Field(default=None, description="替换用户全部角色")
    department: Optional[str] = None


__all__ = [
    "NotifyChannelOut",
    "NotifyChannelUpdateRequest",
    "NotifyChannelTestResult",
    "DictItemOut",
    "DictItemCreateRequest",
    "DictItemUpdateRequest",
    "DictItemListResponse",
    "AdminUserOut",
    "AdminUserListResponse",
    "AdminUserUpdateRequest",
]
