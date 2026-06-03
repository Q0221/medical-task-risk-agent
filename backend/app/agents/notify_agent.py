"""Notify Agent（Phase 8）：多渠道通知调度。

职责：
- 根据 Notification.channel 选择发送渠道（IM / 企业微信 / Email）
- 外部渠道失败时自动降级为 IM（站内消息）
- 更新 Notification.status / sent_at / retry_count / error_message

调用方：
- NotifyWorker：批量轮询 pending/failed 通知并逐条 dispatch
- 直接调用 dispatch_notification(session, notif) 同步单条推送
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.models.enums import NotificationChannel, NotificationStatus
from app.models.notification import Notification
from app.notify import email_channel, im, wxwork
from app.notify.base import NotifyResult

logger = get_logger(__name__)

MAX_RETRY = 3


async def dispatch_notification(
    session: AsyncSession,
    notif: Notification,
) -> NotifyResult:
    """分发单条 Notification，更新其状态，在同一事务内提交。

    渠道降级策略：
      wxwork 失败 → im 兜底
      email  失败 → im 兜底
      im     永不失败（站内消息）
    """
    channel = notif.channel

    if channel == NotificationChannel.WXWORK.value:
        result = await wxwork.dispatch(notif)
        if not result.success:
            logger.warning(
                "wxwork failed (notification_id=%s): %s — fallback to im",
                notif.id, result.error,
            )
            result = await im.dispatch(notif)

    elif channel == NotificationChannel.EMAIL.value:
        result = await email_channel.dispatch(notif)
        if not result.success:
            logger.warning(
                "email failed (notification_id=%s): %s — fallback to im",
                notif.id, result.error,
            )
            result = await im.dispatch(notif)

    else:
        result = await im.dispatch(notif)

    # 更新 Notification 状态
    if result.success:
        notif.status = NotificationStatus.SENT.value
        notif.sent_at = result.sent_at or datetime.now(timezone.utc)
        notif.error_message = None
        logger.info(
            "notification dispatched: id=%s kind=%s channel=%s→%s",
            notif.id, notif.kind, channel, result.channel,
        )
    else:
        notif.retry_count = (notif.retry_count or 0) + 1
        notif.error_message = result.error
        if notif.retry_count >= MAX_RETRY:
            notif.status = NotificationStatus.DEAD.value
            logger.error(
                "notification dead-lettered: id=%s kind=%s retries=%d",
                notif.id, notif.kind, notif.retry_count,
            )
        else:
            notif.status = NotificationStatus.FAILED.value
            logger.warning(
                "notification failed (retry %d/%d): id=%s error=%s",
                notif.retry_count, MAX_RETRY, notif.id, result.error,
            )

    return result


__all__ = ["dispatch_notification", "MAX_RETRY"]
