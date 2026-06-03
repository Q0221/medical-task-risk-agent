"""站内消息渠道（IM）。

站内消息不依赖外部服务：Notification 记录写入 DB 即视为"已送达"。
本模块仅做标记，不发外部请求，因此永远返回成功。
"""

from __future__ import annotations

from app.core.logger import get_logger
from app.notify.base import NotifyResult

logger = get_logger(__name__)


async def dispatch(notif) -> NotifyResult:
    """标记站内消息已送达（无外部请求）。"""
    logger.debug(
        "im dispatch: notification_id=%s kind=%s recipient=%s",
        notif.id, notif.kind, notif.recipient_user_id,
    )
    return NotifyResult.ok(channel="im")
