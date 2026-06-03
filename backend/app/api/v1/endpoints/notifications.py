"""通知接口（Phase 8）。

GET  /notifications          列表（按 user_id / kind / status 过滤，分页）
POST /notifications/{id}/retry  手动重试单条失败通知
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.notify_agent import dispatch_notification
from app.api.deps import db_session
from app.core.exceptions import BizException
from app.core.response import success
from app.models.enums import NotificationStatus
from app.models.notification import Notification
from app.schemas.notification import NotificationListResponse, NotificationOut

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", summary="通知列表")
async def list_notifications(
    user_id: Optional[int] = Query(default=None, description="按收件人 user_id 过滤"),
    task_id: Optional[int] = Query(default=None, description="按关联任务 ID 过滤"),
    kind: Optional[str] = Query(default=None, description="通知类型：task_created / task_reminder / task_overdue 等"),
    status: Optional[str] = Query(default=None, description="状态：pending / sent / failed / dead"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(db_session),
) -> dict:
    """查询通知记录列表，支持按收件人、任务、类型、状态过滤，默认按 created_at 倒序。"""
    base = select(Notification).where(Notification.deleted_at.is_(None))
    count_q = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.deleted_at.is_(None))
    )

    if user_id is not None:
        base = base.where(Notification.recipient_user_id == user_id)
        count_q = count_q.where(Notification.recipient_user_id == user_id)
    if task_id is not None:
        base = base.where(Notification.task_id == task_id)
        count_q = count_q.where(Notification.task_id == task_id)
    if kind:
        base = base.where(Notification.kind == kind)
        count_q = count_q.where(Notification.kind == kind)
    if status:
        base = base.where(Notification.status == status)
        count_q = count_q.where(Notification.status == status)

    total = (await session.execute(count_q)).scalar_one()
    offset = (page - 1) * page_size
    items = (
        await session.execute(
            base.order_by(Notification.created_at.desc()).offset(offset).limit(page_size)
        )
    ).scalars().all()

    return success(
        NotificationListResponse(
            total=total,
            page=page,
            page_size=page_size,
            items=[NotificationOut.model_validate(n) for n in items],
        ).model_dump(mode="json")
    )


@router.post("/{notif_id}/retry", summary="手动重试失败通知")
async def retry_notification(
    notif_id: int = Path(..., ge=1),
    session: AsyncSession = Depends(db_session),
) -> dict:
    """对 status=failed 或 status=dead 的通知立即重试一次。

    重试前会将 retry_count 重置为 0，确保能再次触发发送。
    """
    async with session.begin():
        notif: Optional[Notification] = (
            await session.execute(
                select(Notification).where(
                    Notification.id == notif_id,
                    Notification.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()

        if notif is None:
            raise BizException(code=4044, message=f"通知 id={notif_id} 不存在")

        if notif.status == NotificationStatus.SENT.value:
            raise BizException(code=4090, message="通知已成功发送，无需重试")

        notif.retry_count = 0
        notif.status = NotificationStatus.PENDING.value
        await dispatch_notification(session, notif)

    return success(NotificationOut.model_validate(notif).model_dump(mode="json"))
