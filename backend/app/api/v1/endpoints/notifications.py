"""通知接口（Phase 8 + 通知中心完善）。

GET  /notifications                       列表（按 kind / status 过滤，分页，含 unread_count）
GET  /notifications/unread-count          当前用户未读数
PATCH /notifications/{id}/read            标记单条已读
POST /notifications/batch-read            批量已读（传 ids 或留空表示全部）
POST /notifications/{id}/retry            手动重试失败通知
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.notify_agent import dispatch_notification
from app.api.deps import db_session, get_current_user
from app.core.exceptions import BizException
from app.core.response import success
from app.models.enums import NotificationStatus
from app.models.notification import Notification
from app.models.task import Task
from app.schemas.notification import (
    BatchReadRequest,
    NotificationListResponse,
    NotificationOut,
)
from app.services.auth_service import CurrentUser, is_manager_or_admin

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _recipient_filter(current_user: CurrentUser):
    """当前用户可见的通知条件：收件人是自己 OR 广播（recipient_user_id IS NULL）。"""
    return or_(
        Notification.recipient_user_id == current_user.id,
        Notification.recipient_user_id.is_(None),
    )


def _to_notification_out(notif: Notification, task: Optional[Task]) -> NotificationOut:
    out = NotificationOut.model_validate(notif)
    if task is not None:
        out.task_status = task.status
        out.task_created_at = task.created_at
        out.task_remind_at = task.remind_at
        out.task_due_at = task.due_at
        out.task_title = task.title
        out.task_risk_level = task.risk_level
        out.task_type = task.type
    return out


# ---------------------------------------------------------------------------
# 通知列表
# ---------------------------------------------------------------------------

@router.get("", summary="通知列表（含未读数）")
async def list_notifications(
    user_id: Optional[int] = Query(default=None, description="按收件人 user_id 过滤（管理员可用）"),
    task_id: Optional[int] = Query(default=None, description="按关联任务 ID 过滤"),
    kind: Optional[str] = Query(default=None, description="通知类型"),
    status: Optional[str] = Query(default=None, description="状态"),
    is_read: Optional[bool] = Query(default=None, description="true=只看已读，false=只看未读"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    base_where = [Notification.deleted_at.is_(None)]

    # 权限范围控制
    if user_id is not None:
        if user_id != current_user.id and not is_manager_or_admin(current_user):
            raise BizException(code=4030, message="当前账号无权查看其他用户的通知")
        base_where.append(
            or_(Notification.recipient_user_id == user_id, Notification.recipient_user_id.is_(None))
        )
    elif not is_manager_or_admin(current_user):
        base_where.append(_recipient_filter(current_user))

    if task_id is not None:
        base_where.append(Notification.task_id == task_id)
    if kind:
        base_where.append(Notification.kind == kind)
    if status:
        base_where.append(Notification.status == status)
    if is_read is not None:
        base_where.append(Notification.is_read == is_read)

    total = (
        await session.execute(
            select(func.count(Notification.id)).where(*base_where)
        )
    ).scalar_one()

    # 未读总数（不受 is_read 过滤影响，只受权限和其他条件影响）
    unread_where = [w for w in base_where if not _is_read_filter(w)]
    unread_where.append(Notification.is_read == False)  # noqa: E712
    unread_count = (
        await session.execute(
            select(func.count(Notification.id)).where(*unread_where)
        )
    ).scalar_one()

    rows = (
        await session.execute(
            select(Notification)
            .where(*base_where)
            .order_by(Notification.is_read.asc(), Notification.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    task_ids = [n.task_id for n in rows if n.task_id]
    task_map: dict = {}
    if task_ids:
        task_rows = (
            await session.execute(
                select(Task).where(Task.id.in_(task_ids), Task.deleted_at.is_(None))
            )
        ).scalars().all()
        task_map = {t.id: t for t in task_rows}

    return success(
        NotificationListResponse(
            total=total,
            page=page,
            page_size=page_size,
            unread_count=unread_count,
            items=[_to_notification_out(n, task_map.get(n.task_id)) for n in rows],
        ).model_dump(mode="json")
    )


def _is_read_filter(clause) -> bool:
    """粗略判断一个 where 子句是否是 is_read 过滤（用于构造 unread_count 子查询时排除）。"""
    try:
        return "is_read" in str(clause)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 未读数（轻量接口，用于角标轮询）
# ---------------------------------------------------------------------------

@router.get("/unread-count", summary="获取当前用户未读通知数")
async def get_unread_count(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    count = (
        await session.execute(
            select(func.count(Notification.id)).where(
                Notification.deleted_at.is_(None),
                Notification.is_read == False,  # noqa: E712
                _recipient_filter(current_user),
            )
        )
    ).scalar_one()
    return success({"count": count})


# ---------------------------------------------------------------------------
# 标记单条已读
# ---------------------------------------------------------------------------

@router.patch("/{notif_id}/read", summary="标记单条通知已读")
async def mark_notification_read(
    notif_id: int = Path(..., ge=1),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
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

        if (
            notif.recipient_user_id not in (None, current_user.id)
            and not is_manager_or_admin(current_user)
        ):
            raise BizException(code=4030, message="当前账号无权操作该通知")

        notif.is_read = True

    return success({"id": notif_id, "is_read": True})


# ---------------------------------------------------------------------------
# 批量已读
# ---------------------------------------------------------------------------

@router.post("/batch-read", summary="批量标记通知已读")
async def batch_mark_read(
    body: BatchReadRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    """传入 ids 则仅标记这些通知；不传则标记当前用户全部未读通知。"""
    async with session.begin():
        where = [
            Notification.deleted_at.is_(None),
            Notification.is_read == False,  # noqa: E712
        ]

        if body.ids:
            where.append(Notification.id.in_(body.ids))
        else:
            # 无指定 ids → 标记当前用户所有未读
            where.append(_recipient_filter(current_user))

        result = await session.execute(
            update(Notification)
            .where(*where)
            .values(is_read=True)
            .execution_options(synchronize_session=False)
        )
        affected = result.rowcount

    return success({"marked": affected})


# ---------------------------------------------------------------------------
# 手动重试失败通知
# ---------------------------------------------------------------------------

@router.post("/{notif_id}/retry", summary="手动重试失败通知")
async def retry_notification(
    notif_id: int = Path(..., ge=1),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
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

        if (
            notif.recipient_user_id not in (None, current_user.id)
            and not is_manager_or_admin(current_user)
        ):
            raise BizException(code=4030, message="当前账号无权重试该通知")

        if notif.status == NotificationStatus.SENT.value:
            raise BizException(code=4090, message="通知已成功发送，无需重试")

        notif.retry_count = 0
        notif.status = NotificationStatus.PENDING.value
        await dispatch_notification(session, notif)

    return success(NotificationOut.model_validate(notif).model_dump(mode="json"))
