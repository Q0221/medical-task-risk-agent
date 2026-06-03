"""任务接口。

已实现：
- GET    /tasks/pending-review:     待审核任务列表（Phase 5）
- GET    /tasks/{id}:               任务详情
- GET    /tasks:                    任务列表
- POST   /tasks/{id}/review:        人工审核决策（Phase 5）
- POST   /tasks/{id}/remind:        设置/更新提醒（Phase 7）
- DELETE /tasks/{id}/remind:        取消提醒（Phase 7）
- PATCH  /tasks/{id}/complete:      完成任务（Phase 10）
- PATCH  /tasks/{id}/cancel:        取消任务（Phase 10）
- PATCH  /tasks/{id}/assign:        重新分配任务（Phase 10）
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Path, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, redis_client
from app.core.exceptions import BizException
from app.core.response import success
from app.schemas.task import (
    TaskAssignRequest,
    TaskCancelRequest,
    TaskCompleteRequest,
    TaskDetail,
    TaskListItem,
    TaskListResponse,
    TaskRemindRequest,
    TaskRemindResult,
    TaskReviewRequest,
)
from app.services import task_service
from app.services.reminder_service import (
    cancel_deadline,
    cancel_reminder,
    schedule_deadline,
    schedule_reminder,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/pending-review", summary="待审核任务列表（Phase 5）")
async def list_pending_review(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(db_session),
) -> dict:
    items, total = await task_service.list_pending_review(
        session, page=page, page_size=page_size
    )
    resp = TaskListResponse(
        items=[TaskListItem.model_validate(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
    )
    return success(resp.model_dump(mode="json"))


@router.get("/{task_id}", summary="任务详情")
async def get_task_detail(
    task_id: int = Path(..., ge=1),
    session: AsyncSession = Depends(db_session),
) -> dict:
    task = await task_service.get_task(session, task_id)
    if task is None:
        raise BizException(code=4044, message=f"任务 id={task_id} 不存在")
    return success(TaskDetail.model_validate(task).model_dump(mode="json"))


@router.get("", summary="任务列表")
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    assignee_id: Optional[int] = Query(default=None, ge=1),
    status: Optional[str] = Query(default=None),
    risk_level: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(db_session),
) -> dict:
    items, total = await task_service.list_tasks(
        session,
        page=page,
        page_size=page_size,
        assignee_id=assignee_id,
        status=status,
        risk_level=risk_level,
    )
    resp = TaskListResponse(
        items=[TaskListItem.model_validate(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
    )
    return success(resp.model_dump(mode="json"))


@router.post("/{task_id}/review", summary="人工审核决策（Phase 5）")
async def review_task(
    task_id: int = Path(..., ge=1),
    body: TaskReviewRequest = ...,
    session: AsyncSession = Depends(db_session),
) -> dict:
    """对 review_status=pending 的高风险任务执行审核决策。

    - **approved**：通过，任务放行回 `pending` 状态，责任人可继续处理。
    - **rejected**：驳回，任务变为 `cancelled`。
    - **escalated**：升级上报，任务保持 `awaiting_review`，等待更高层级审核。
    """
    async with session.begin():
        result = await task_service.review_task(session, task_id, body)
    return success(result.model_dump(mode="json"))


@router.post("/{task_id}/remind", summary="设置/更新任务提醒（Phase 7）")
async def set_remind(
    task_id: int = Path(..., ge=1),
    body: TaskRemindRequest = ...,
    session: AsyncSession = Depends(db_session),
    redis: Redis = Depends(redis_client),
) -> dict:
    """设置或更新任务的提醒时间（`remind_at`），并可选更新截止时间（`due_at`）。

    提醒时间到期后，Worker 会自动在 `notifications` 表写一条
    `task_reminder` 记录，Phase 8 的 Notify Agent 负责实际推送。
    """
    async with session.begin():
        task = await task_service.get_task(session, task_id)
        if task is None:
            raise BizException(code=4044, message=f"任务 id={task_id} 不存在")
        task.remind_at = body.remind_at
        if body.due_at is not None:
            task.due_at = body.due_at
        await session.flush()
        await session.refresh(task)

    # 注册到 Redis ZSet（幂等，重复 zadd 会更新 score）
    await schedule_reminder(redis, task_id, body.remind_at)
    if body.due_at is not None:
        await schedule_deadline(redis, task_id, body.due_at)

    return success(TaskRemindResult(
        task_id=task_id,
        remind_at=body.remind_at,
        due_at=body.due_at,
        message="提醒已设置",
    ).model_dump(mode="json"))


@router.delete("/{task_id}/remind", summary="取消任务提醒（Phase 7）")
async def cancel_remind(
    task_id: int = Path(..., ge=1),
    session: AsyncSession = Depends(db_session),
    redis: Redis = Depends(redis_client),
) -> dict:
    """取消任务的提醒（从 Redis ZSet 移除，不清除 tasks.remind_at 字段快照）。"""
    async with session.begin():
        task = await task_service.get_task(session, task_id)
        if task is None:
            raise BizException(code=4044, message=f"任务 id={task_id} 不存在")

    await cancel_reminder(redis, task_id)
    await cancel_deadline(redis, task_id)

    return success({"task_id": task_id, "message": "提醒已取消"})


# ===========================================================================
# Phase 10: 任务生命周期接口
# ===========================================================================

@router.patch("/{task_id}/complete", summary="完成任务（Phase 10）")
async def complete_task(
    task_id: int = Path(..., ge=1),
    body: TaskCompleteRequest = ...,
    session: AsyncSession = Depends(db_session),
    redis: Redis = Depends(redis_client),
) -> dict:
    """将任务标记为已完成。

    仅允许 status ∈ {pending, in_progress, blocked} 时操作；
    完成后自动从 Redis ZSet 中移除提醒和截止时间追踪。
    """
    async with session.begin():
        task = await task_service.complete_task(
            session,
            task_id,
            operator_id=body.operator_id,
            comment=body.comment,
        )

    # 清除 Redis 提醒和截止追踪
    await cancel_reminder(redis, task_id)
    await cancel_deadline(redis, task_id)

    return success(TaskDetail.model_validate(task).model_dump(mode="json"))


@router.patch("/{task_id}/cancel", summary="取消任务（Phase 10）")
async def cancel_task(
    task_id: int = Path(..., ge=1),
    body: TaskCancelRequest = ...,
    session: AsyncSession = Depends(db_session),
    redis: Redis = Depends(redis_client),
) -> dict:
    """取消任务（已完成 / 已取消不可再操作）。

    取消后自动从 Redis ZSet 中移除提醒和截止时间追踪。
    """
    async with session.begin():
        task = await task_service.cancel_task(
            session,
            task_id,
            operator_id=body.operator_id,
            reason=body.reason,
        )

    await cancel_reminder(redis, task_id)
    await cancel_deadline(redis, task_id)

    return success(TaskDetail.model_validate(task).model_dump(mode="json"))


@router.patch("/{task_id}/assign", summary="重新分配任务负责人（Phase 10）")
async def assign_task(
    task_id: int = Path(..., ge=1),
    body: TaskAssignRequest = ...,
    session: AsyncSession = Depends(db_session),
) -> dict:
    """重新分配任务负责人（已完成/已取消不可操作）。

    同时写入分配事件和站内通知给新负责人。
    提供 `assignee_id`（user_id）或 `assignee_name`（模糊匹配）二选一。
    """
    async with session.begin():
        task = await task_service.assign_task(
            session,
            task_id,
            assignee_id=body.assignee_id,
            assignee_name=body.assignee_name,
            operator_id=body.operator_id,
            comment=body.comment,
        )

    return success(TaskDetail.model_validate(task).model_dump(mode="json"))
