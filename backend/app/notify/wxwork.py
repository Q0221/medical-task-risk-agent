"""企业微信渠道（群机器人 Webhook）。

配置：
  WXWORK_WEBHOOK_URL  企业微信机器人 Webhook 地址（不配置则跳过）
  WXWORK_MENTION_ALL  推送时是否 @所有人（默认 False）

Webhook 文档：
  https://developer.work.weixin.qq.com/document/path/91770

返回值 errcode==0 表示成功。未配置 Webhook 时降级返回 fail，
由 notify_agent 兜底至 IM 渠道。
"""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logger import get_logger
from app.notify.base import NotifyResult

logger = get_logger(__name__)

_TIMEOUT = 10  # 秒


async def dispatch(notif) -> NotifyResult:
    """向企业微信机器人 Webhook 推送文本消息。"""
    webhook_url = getattr(settings, "WXWORK_WEBHOOK_URL", "")
    if not webhook_url:
        return NotifyResult.fail("wxwork", "WXWORK_WEBHOOK_URL not configured")

    title = notif.title or "任务通知"
    content = notif.content or ""
    full_text = f"【{title}】\n{content}"

    mention_all = getattr(settings, "WXWORK_MENTION_ALL", False)
    payload: dict = {
        "msgtype": "text",
        "text": {
            "content": full_text,
        },
    }
    if mention_all:
        payload["text"]["mentioned_list"] = ["@all"]

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(webhook_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if data.get("errcode") == 0:
                logger.info(
                    "wxwork sent: notification_id=%s kind=%s",
                    notif.id, notif.kind,
                )
                return NotifyResult.ok(channel="wxwork")
            else:
                err = f"errcode={data.get('errcode')} errmsg={data.get('errmsg')}"
                logger.warning("wxwork api error: %s", err)
                return NotifyResult.fail("wxwork", err)
    except Exception as exc:
        logger.warning("wxwork request failed: %s", exc)
        return NotifyResult.fail("wxwork", str(exc))
