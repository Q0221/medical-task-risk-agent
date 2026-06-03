"""通知渠道基础类型。

NotifyResult: 渠道发送结果；所有 channel 模块返回此类型。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class NotifyResult:
    """渠道发送结果。"""

    success: bool
    channel: str
    sent_at: Optional[datetime] = None
    error: Optional[str] = None

    @classmethod
    def ok(cls, channel: str) -> "NotifyResult":
        return cls(success=True, channel=channel, sent_at=datetime.now(timezone.utc))

    @classmethod
    def fail(cls, channel: str, error: str) -> "NotifyResult":
        return cls(success=False, channel=channel, error=error)
