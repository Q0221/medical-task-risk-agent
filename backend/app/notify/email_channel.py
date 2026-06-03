"""邮件渠道（SMTP）。

配置（支持 SSL 和 STARTTLS）：
  SMTP_HOST      SMTP 服务器地址（空字符串 = 不启用）
  SMTP_PORT      端口（465 = SSL，587 = STARTTLS，25 = 无加密）
  SMTP_USER      登录用户名
  SMTP_PASSWORD  登录密码
  SMTP_FROM      发件人地址（默认与 SMTP_USER 相同）
  SMTP_USE_SSL   True = SSL（465），False = STARTTLS（587）

未配置 SMTP_HOST 时降级返回 fail，由 notify_agent 兜底至 IM 渠道。
使用 asyncio.to_thread 包装同步 smtplib 调用，保持异步事件循环畅通。
"""

from __future__ import annotations

import asyncio
import smtplib
from email.mime.text import MIMEText

from app.core.config import settings
from app.core.logger import get_logger
from app.notify.base import NotifyResult

logger = get_logger(__name__)


def _send_sync(to_addr: str, title: str, content: str) -> None:
    """同步 SMTP 发送（在线程中执行）。"""
    smtp_host: str = getattr(settings, "SMTP_HOST", "")
    smtp_port: int = int(getattr(settings, "SMTP_PORT", 465))
    smtp_user: str = getattr(settings, "SMTP_USER", "")
    smtp_password: str = getattr(settings, "SMTP_PASSWORD", "")
    smtp_from: str = getattr(settings, "SMTP_FROM", smtp_user)
    use_ssl: bool = bool(getattr(settings, "SMTP_USE_SSL", True))

    msg = MIMEText(content, "plain", "utf-8")
    msg["Subject"] = title
    msg["From"] = smtp_from
    msg["To"] = to_addr

    if use_ssl:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as server:
            if smtp_user:
                server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, [to_addr], msg.as_string())
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            if smtp_user:
                server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, [to_addr], msg.as_string())


async def dispatch(notif) -> NotifyResult:
    """异步发送邮件（在线程池中调用同步 smtplib）。"""
    smtp_host: str = getattr(settings, "SMTP_HOST", "")
    if not smtp_host:
        return NotifyResult.fail("email", "SMTP_HOST not configured")

    to_addr = notif.recipient_address
    if not to_addr or "@" not in to_addr:
        return NotifyResult.fail("email", f"invalid recipient_address: {to_addr!r}")

    title = notif.title or "任务通知"
    content = notif.content or ""
    try:
        await asyncio.to_thread(_send_sync, to_addr, title, content)
        logger.info(
            "email sent: notification_id=%s to=%s", notif.id, to_addr
        )
        return NotifyResult.ok(channel="email")
    except Exception as exc:
        logger.warning("email send failed: %s", exc)
        return NotifyResult.fail("email", str(exc))
