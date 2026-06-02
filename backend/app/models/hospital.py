"""医院客户主数据。

risk_score 用于 Risk Agent 在长期记忆里对历史风险的加权依据。
"""

from typing import Optional

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class Hospital(BaseModel):
    __tablename__ = "hospitals"

    code: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, comment="内部编码"
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    level: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True, comment="医院等级：三甲/三乙/...等"
    )
    region: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    risk_score: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="历史风险分，0-100"
    )
    contact_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
