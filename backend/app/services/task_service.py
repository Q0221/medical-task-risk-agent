"""任务服务层：任务持久化 + 事件流写入。

关键设计：
- create_from_draft 是 Agent 落库入口，单事务内同时写入 tasks + task_events。
- 名称解析（hospital_name/product_name/assignee_name）在此处完成，
  避免污染 Agent 节点。
- review_task 实现 Phase 5 Human-in-the-loop 审核决策落库。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizException
from app.core.logger import get_logger
from app.models.enums import (
    BusinessObjectType,
    NotificationChannel,
    NotificationKind,
    NotificationStatus,
    ReviewStatus,
    RiskLevel,
    TaskEventType,
    TaskPriority,
    TaskStatus,
    TaskType,
)
from app.models.hospital import Hospital
from app.models.notification import Notification
from app.models.product import Product
from app.models.risk_record import RiskRecord
from app.models.task import Task
from app.models.task_event import TaskEvent
from app.services.user_service import find_user_by_name, get_default_user, get_user_by_id
from app.schemas.task import TaskDraft, TaskReviewRequest, TaskReviewResult

logger = get_logger(__name__)


async def _resolve_hospital(
    session: AsyncSession, name: Optional[str]
) -> Optional[Hospital]:
    if not name:
        return None
    return (
        await session.execute(
            select(Hospital)
            .where(Hospital.name.like(f"%{name.strip()}%"), Hospital.deleted_at.is_(None))
            .limit(1)
        )
    ).scalar_one_or_none()


async def _resolve_product(
    session: AsyncSession, name: Optional[str]
) -> Optional[Product]:
    if not name:
        return None
    return (
        await session.execute(
            select(Product)
            .where(Product.name.like(f"%{name.strip()}%"), Product.deleted_at.is_(None))
            .limit(1)
        )
    ).scalar_one_or_none()


async def create_from_draft(
    session: AsyncSession,
    draft: TaskDraft,
    *,
    creator_user_id: Optional[int] = None,
    trace_id: Optional[str] = None,
    agent_session_id: Optional[str] = None,
) -> Task:
    """根据 Agent 抽取的 TaskDraft 创建任务，同事务写入 create 事件。

    名称解析失败时：
    - assignee_name 找不到 → 抛 BizException(4040)，由上层提示用户。
    - hospital/product 找不到 → 仅打日志，字段置空，不阻塞任务创建。
    """
    if creator_user_id is not None:
        creator = await get_user_by_id(session, creator_user_id)
        if creator is None:
            raise BizException(code=4041, message=f"创建人 user_id={creator_user_id} 不存在")
    else:
        creator = await get_default_user(session)

    if draft.assignee_name:
        assignee = await find_user_by_name(session, draft.assignee_name)
        if assignee is None:
            raise BizException(
                code=4042,
                message=f"找不到责任人「{draft.assignee_name}」，请确认员工姓名是否正确",
            )
    else:
        assignee = creator

    hospital = await _resolve_hospital(session, draft.hospital_name)
    if draft.hospital_name and hospital is None:
        logger.info("hospital not found, skip linking: %s", draft.hospital_name)

    product = await _resolve_product(session, draft.product_name)
    if draft.product_name and product is None:
        logger.info("product not found, skip linking: %s", draft.product_name)

    task = Task(
        type=_as_value(draft.type, TaskType.OTHER),
        title=draft.title,
        description=draft.description,
        source="agent",
        status=TaskStatus.PENDING.value,
        priority=_as_value(draft.priority, TaskPriority.MEDIUM),
        assignee_id=assignee.id,
        created_by=creator.id,
        hospital_id=hospital.id if hospital else None,
        product_id=product.id if product else None,
        business_object_type=_as_value(draft.business_object_type, BusinessObjectType.NONE),
        business_object_id=draft.business_object_id,
        remind_at=draft.remind_at,
        due_at=draft.due_at,
        risk_level=RiskLevel.LOW.value,
        review_status=ReviewStatus.NONE.value,
        trace_id=trace_id,
        agent_session_id=agent_session_id,
        extra={"risk_keywords": draft.risk_keywords} if draft.risk_keywords else None,
    )
    session.add(task)
    await session.flush()

    session.add(
        TaskEvent(
            task_id=task.id,
            event_type=TaskEventType.CREATE.value,
            operator_id=creator.id,
            operator_kind="agent",
            payload={
                "draft": draft.model_dump(mode="json"),
                "resolved": {
                    "assignee_id": assignee.id,
                    "hospital_id": hospital.id if hospital else None,
                    "product_id": product.id if product else None,
                },
            },
            trace_id=trace_id,
        )
    )
    await session.flush()

    # 写 task_created 通知（站内消息，NotifyWorker 会分发）
    _notify_channel = getattr(
        __import__("app.core.config", fromlist=["settings"]).settings,
        "DEFAULT_NOTIFY_CHANNEL",
        NotificationChannel.IM.value,
    )
    session.add(
        Notification(
            task_id=task.id,
            kind=NotificationKind.TASK_CREATED.value,
            channel=_notify_channel,
            recipient_user_id=assignee.id,
            recipient_address=getattr(assignee, "email", None),
            title=f"新任务已分配：{task.title}",
            content=(
                f"任务类型：{task.type}\n"
                f"优先级：{task.priority}\n"
                f"描述：{task.description or '（无）'}\n"
                f"截止时间：{task.due_at.strftime('%Y-%m-%d %H:%M') if task.due_at else '未设置'}"
            ),
            status=NotificationStatus.PENDING.value,
            trace_id=trace_id,
        )
    )
    await session.flush()

    # server_default 列（created_at/updated_at）需要 refresh 才能读回 Python 内存，
    # 否则离开 async 上下文后读取会触发懒加载 -> MissingGreenlet
    await session.refresh(task)
    logger.info("task created: id=%s title=%s trace_id=%s", task.id, task.title, trace_id)
    return task


async def get_task(session: AsyncSession, task_id: int) -> Optional[Task]:
    return (
        await session.execute(
            select(Task).where(Task.id == task_id, Task.deleted_at.is_(None))
        )
    ).scalar_one_or_none()


async def list_tasks(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    assignee_id: Optional[int] = None,
    status: Optional[str] = None,
    risk_level: Optional[str] = None,
) -> tuple[Sequence[Task], int]:
    page = max(1, page)
    page_size = max(1, min(100, page_size))

    base = select(Task).where(Task.deleted_at.is_(None))
    count_q = select(func.count()).select_from(Task).where(Task.deleted_at.is_(None))

    if assignee_id is not None:
        base = base.where(Task.assignee_id == assignee_id)
        count_q = count_q.where(Task.assignee_id == assignee_id)
    if status:
        base = base.where(Task.status == status)
        count_q = count_q.where(Task.status == status)
    if risk_level:
        base = base.where(Task.risk_level == risk_level)
        count_q = count_q.where(Task.risk_level == risk_level)

    items = (
        (
            await session.execute(
                base.order_by(Task.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    total = (await session.execute(count_q)).scalar_one()
    return items, int(total)


async def review_task(
    session: AsyncSession,
    task_id: int,
    req: TaskReviewRequest,
) -> TaskReviewResult:
    """Human-in-the-loop 审核决策（Phase 5）。

    状态机：
    - approved  → review_status=approved,  task status=pending（放行，等待责任人处理）
    - rejected  → review_status=rejected,  task status=cancelled
    - escalated → review_status=escalated, task status=awaiting_review（保持阻塞，上报更高层级）

    同时更新最近一条 pending 的 risk_records，写 RISK_REVIEW_DECIDE 事件。
    调用方需在事务内调用此函数。
    """
    task = await get_task(session, task_id)
    if task is None:
        raise BizException(code=4044, message=f"任务 id={task_id} 不存在")

    if task.review_status != ReviewStatus.PENDING.value:
        raise BizException(
            code=4090,
            message=f"任务 id={task_id} 当前审核状态为 {task.review_status!r}，仅 pending 状态可审核",
        )

    reviewer = await get_user_by_id(session, req.reviewer_id)
    if reviewer is None:
        raise BizException(code=4041, message=f"审核人 user_id={req.reviewer_id} 不存在")

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # 计算新状态
    action_to_review = {
        "approved": ReviewStatus.APPROVED.value,
        "rejected": ReviewStatus.REJECTED.value,
        "escalated": ReviewStatus.ESCALATED.value,
    }
    action_to_task_status = {
        "approved": TaskStatus.PENDING.value,
        "rejected": TaskStatus.CANCELLED.value,
        "escalated": TaskStatus.AWAITING_REVIEW.value,
    }
    action_messages = {
        "approved": "审核通过，任务已放行",
        "rejected": "审核驳回，任务已取消",
        "escalated": "已升级上报，等待更高层级审核",
    }

    new_review_status = action_to_review[req.action]
    new_task_status = action_to_task_status[req.action]

    task.review_status = new_review_status
    task.status = new_task_status
    task.reviewer_id = req.reviewer_id
    task.reviewed_at = now
    task.review_comment = req.comment

    # 更新最近一条 pending risk_record
    risk_record = (
        await session.execute(
            select(RiskRecord)
            .where(
                RiskRecord.task_id == task_id,
                RiskRecord.review_status == ReviewStatus.PENDING.value,
                RiskRecord.deleted_at.is_(None),
            )
            .order_by(RiskRecord.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if risk_record is not None:
        risk_record.review_status = new_review_status
        risk_record.reviewer_id = req.reviewer_id
        risk_record.reviewed_at = now
        risk_record.review_comment = req.comment

    session.add(
        TaskEvent(
            task_id=task_id,
            event_type=TaskEventType.RISK_REVIEW_DECIDE.value,
            operator_id=req.reviewer_id,
            operator_kind="user",
            payload={
                "action": req.action,
                "review_status": new_review_status,
                "task_status": new_task_status,
                "comment": req.comment,
            },
            trace_id=task.trace_id,
        )
    )

    await session.flush()
    await session.refresh(task)
    logger.info(
        "task reviewed: id=%s action=%s review_status=%s task_status=%s reviewer=%s",
        task_id,
        req.action,
        new_review_status,
        new_task_status,
        req.reviewer_id,
    )

    return TaskReviewResult(
        task_id=task_id,
        review_status=new_review_status,
        task_status=new_task_status,
        reviewer_id=req.reviewer_id,
        reviewed_at=now,
        message=action_messages[req.action],
    )


async def list_pending_review(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[Sequence[Task], int]:
    """返回所有 review_status=pending 的待审核任务列表。"""
    page = max(1, page)
    page_size = max(1, min(100, page_size))

    base = select(Task).where(
        Task.review_status == ReviewStatus.PENDING.value,
        Task.deleted_at.is_(None),
    )
    count_q = select(func.count()).select_from(Task).where(
        Task.review_status == ReviewStatus.PENDING.value,
        Task.deleted_at.is_(None),
    )

    items = (
        (
            await session.execute(
                base.order_by(Task.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    total = (await session.execute(count_q)).scalar_one()
    return items, int(total)


# ---------------------------------------------------------------------------
# Phase 10: 任务生命周期 — complete / cancel / assign
# ---------------------------------------------------------------------------

_COMPLETABLE = {TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value, TaskStatus.BLOCKED.value}
_UNCLOSABLE  = {TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value}


async def complete_task(
    session: AsyncSession,
    task_id: int,
    *,
    operator_id: Optional[int] = None,
    comment: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> Task:
    """将任务标记为已完成。

    仅允许 status ∈ {pending, in_progress, blocked} 时操作。
    """
    task = await get_task(session, task_id)
    if task is None:
        raise BizException(code=4044, message=f"任务 id={task_id} 不存在")
    if task.status not in _COMPLETABLE:
        raise BizException(
            code=4090,
            message=f"任务当前状态 {task.status!r} 不允许完成操作，仅支持 {sorted(_COMPLETABLE)}",
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task.status = TaskStatus.COMPLETED.value
    task.completed_at = now

    session.add(TaskEvent(
        task_id=task_id,
        event_type=TaskEventType.COMPLETE.value,
        operator_id=operator_id,
        operator_kind="user" if operator_id else "system",
        payload={"comment": comment},
        trace_id=trace_id,
    ))
    await session.flush()
    await session.refresh(task)
    logger.info("task completed: id=%s operator=%s", task_id, operator_id)
    return task


async def cancel_task(
    session: AsyncSession,
    task_id: int,
    *,
    operator_id: Optional[int] = None,
    reason: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> Task:
    """取消任务（已完成 / 已取消不可再操作）。"""
    task = await get_task(session, task_id)
    if task is None:
        raise BizException(code=4044, message=f"任务 id={task_id} 不存在")
    if task.status in _UNCLOSABLE:
        raise BizException(
            code=4090,
            message=f"任务当前状态 {task.status!r}，无法取消",
        )

    task.status = TaskStatus.CANCELLED.value

    session.add(TaskEvent(
        task_id=task_id,
        event_type=TaskEventType.CANCEL.value,
        operator_id=operator_id,
        operator_kind="user" if operator_id else "system",
        payload={"reason": reason},
        trace_id=trace_id,
    ))
    await session.flush()
    await session.refresh(task)
    logger.info("task cancelled: id=%s operator=%s reason=%s", task_id, operator_id, reason)
    return task


async def assign_task(
    session: AsyncSession,
    task_id: int,
    *,
    assignee_id: Optional[int] = None,
    assignee_name: Optional[str] = None,
    operator_id: Optional[int] = None,
    comment: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> Task:
    """重新分配任务负责人（已完成/已取消不可操作）。"""
    task = await get_task(session, task_id)
    if task is None:
        raise BizException(code=4044, message=f"任务 id={task_id} 不存在")
    if task.status in _UNCLOSABLE:
        raise BizException(
            code=4090,
            message=f"任务当前状态 {task.status!r}，无法重新分配",
        )

    # 解析负责人
    if assignee_id is not None:
        new_assignee = await get_user_by_id(session, assignee_id)
        if new_assignee is None:
            raise BizException(code=4041, message=f"负责人 user_id={assignee_id} 不存在")
    elif assignee_name:
        new_assignee = await find_user_by_name(session, assignee_name)
        if new_assignee is None:
            raise BizException(code=4042, message=f"找不到负责人「{assignee_name}」")
    else:
        raise BizException(code=4000, message="需提供 assignee_id 或 assignee_name")

    old_assignee_id = task.assignee_id
    task.assignee_id = new_assignee.id

    session.add(TaskEvent(
        task_id=task_id,
        event_type=TaskEventType.ASSIGN.value,
        operator_id=operator_id,
        operator_kind="user" if operator_id else "system",
        payload={
            "old_assignee_id": old_assignee_id,
            "new_assignee_id": new_assignee.id,
            "new_assignee_name": new_assignee.name,
            "comment": comment,
        },
        trace_id=trace_id,
    ))

    # 写通知给新负责人
    from app.core.config import settings as _settings
    session.add(Notification(
        task_id=task_id,
        kind=NotificationKind.TASK_CREATED.value,
        channel=getattr(_settings, "DEFAULT_NOTIFY_CHANNEL", NotificationChannel.IM.value),
        recipient_user_id=new_assignee.id,
        recipient_address=getattr(new_assignee, "email", None),
        title=f"任务已分配给您：{task.title}",
        content=(
            f"任务已由 user_id={operator_id} 重新分配给您。\n"
            f"任务类型：{task.type}\n"
            f"备注：{comment or '（无）'}"
        ),
        status=NotificationStatus.PENDING.value,
        trace_id=trace_id,
    ))

    await session.flush()
    await session.refresh(task)
    logger.info(
        "task assigned: id=%s old_assignee=%s new_assignee=%s operator=%s",
        task_id, old_assignee_id, new_assignee.id, operator_id,
    )
    return task


def _as_value(maybe_enum, default) -> str:
    """字符串 / Enum 统一转为字符串值。"""
    if maybe_enum is None:
        return default.value
    if hasattr(maybe_enum, "value"):
        return maybe_enum.value
    return str(maybe_enum)


# 暴露 datetime 让上层可以构造默认值
__all__ = [
    "create_from_draft",
    "get_task",
    "list_tasks",
    "review_task",
    "list_pending_review",
    "complete_task",
    "cancel_task",
    "assign_task",
    "datetime",
]
