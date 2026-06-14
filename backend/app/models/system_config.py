"""系统配置表（通用 KV 存储）。

category 值：
- notify_channel : 通知渠道配置（wxwork / email / im）
- dictionary     : 业务字典（超时时间、重试次数等可调参数）
- system         : 系统级开关（预留）

通过 category + config_key 唯一定位一条配置。
"""

from typing import Optional

from sqlalchemy import JSON, Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class SystemConfig(BaseModel):
    __tablename__ = "system_configs"
    __table_args__ = (
        UniqueConstraint("category", "config_key", name="uq_system_config_cat_key"),
    )

    category: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True,
        comment="notify_channel | dictionary | system",
    )
    config_key: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="配置键名"
    )
    label: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="展示名称"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="说明"
    )
    config_value: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, comment="配置值（JSON 对象）"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
