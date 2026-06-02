"""产品主数据。"""

from typing import Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class Product(BaseModel):
    __tablename__ = "products"

    code: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, comment="产品编码"
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    category: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True, comment="产品类别"
    )
    business_unit: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="所属事业部"
    )
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
