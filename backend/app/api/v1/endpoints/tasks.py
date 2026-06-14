"""任务接口。

已实现：
- GET    /tasks/pending-review:          待审核任务列表
- GET    /tasks/{id}:                    任务详情
- GET    /tasks:                         任务列表（含高级筛选）
- POST   /tasks/{id}/review:             人工审核决策
- POST   /tasks/{id}/remind:             设置/更新提醒
- DELETE /tasks/{id}/remind:             取消提醒
- PATCH  /tasks/{id}/complete:           完成任务
- PATCH  /tasks/{id}/cancel:             取消任务
- PATCH  /tasks/{id}/assign:             重新分配任务
- GET    /tasks/{id}/timeline:           事件时间线
- POST   /tasks/{id}/comments:           添加评论
- POST   /tasks/{id}/attachments:        记录附件元数据
- PATCH  /tasks/{id}/collaborators:      更新协作者
- POST   /tasks/batch/complete:          批量完成
- POST   /tasks/batch/cancel:            批量取消
- POST   /tasks/batch/assign:            批量分配
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_current_user, redis_client, require_app_roles
from app.core.exceptions import BizException
from app.core.response import success
from app.schemas.task import (
    TaskAssignRequest,
    TaskAttachmentRequest,
    TaskBatchAssignRequest,
    TaskBatchCancelRequest,
    TaskBatchCompleteRequest,
    TaskBatchResult,
    TaskCancelRequest,
    TaskCollaboratorRequest,
    TaskCommentOut,
    TaskCommentRequest,
    TaskCompleteRequest,
    TaskDetail,
    TaskEventOut,
    TaskListItem,
    TaskListResponse,
    TaskRemindRequest,
    TaskRemindResult,
    TaskReviewRequest,
    TaskTimelineResponse,
)
from app.services import task_service
from app.services.auth_service import CurrentUser, is_manager_or_admin
from app.services.reminder_service import (
    cancel_deadline,
    cancel_reminder,
    schedule_deadline,
    schedule_reminder,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


# ---------------------------------------------------------------------------
# 权限辅助
# ---------------------------------------------------------------------------

def _ensure_task_visible(task, current_user: CurrentUser) -> None:
    if (
        is_manager_or_admin(current_user)
        or task.assignee_id == current_user.id
        or task.created_by == current_user.id
        or (task.collaborators and current_user.id in task.collaborators)
    ):
        return
    raise BizException(code=4030, message="当前账号无权查看该任务")


def _ensure_task_handler(task, current_user: CurrentUser) -> None:
    if is_manager_or_admin(current_user) or task.assignee_id == current_user.id:
        return
    raise BizException(code=4030, message="当前账号无权处理该任务")


def _ensure_task_owner_or_manager(task, current_user: CurrentUser) -> None:
    if (
        is_manager_or_admin(current_user)
        or task.assignee_id == current_user.id
        or task.created_by == current_user.id
    ):
        return
    raise BizException(code=4030, message="当前账号无权变更该任务")


# ---------------------------------------------------------------------------
# 批量操作（路径不含 {task_id}，放在最前避免被参数路由截获）
# ---------------------------------------------------------------------------

@router.post("/batch/complete", summary="批量完成任务")
async def batch_complete(
    body: TaskBatchCompleteRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
    redis: Redis = Depends(redis_client),
) -> dict:
    """仅允许完成自己负责的任务；manager/admin 可操作任意任务。"""
    async with session.begin():
        succeeded, failed = await task_service.batch_complete(
            session,
            body.task_ids,
            operator_id=current_user.id,
            comment=body.comment,
            is_manager=is_manager_or_admin(current_user),
        )
    for tid in succeeded:
        await cancel_reminder(redis, tid)
        await cancel_deadline(redis, tid)
    result = TaskBatchResult(
        succeeded=succeeded,
        failed=failed,
        message=f"成功完成 {len(succeeded)} 条，失败/跳过 {len(failed)} 条",
    )
    return success(result.model_dump(mode="json"))


@router.post("/batch/cancel", summary="批量取消任务")
async def batch_cancel(
    body: TaskBatchCancelRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
    redis: Redis = Depends(redis_client),
) -> dict:
    async with session.begin():
        succeeded, failed = await task_service.batch_cancel(
            session,
            body.task_ids,
            operator_id=current_user.id,
            reason=body.reason,
            is_manager=is_manager_or_admin(current_user),
        )
    for tid in succeeded:
        await cancel_reminder(redis, tid)
        await cancel_deadline(redis, tid)
    result = TaskBatchResult(
        succeeded=succeeded,
        failed=failed,
        message=f"成功取消 {len(succeeded)} 条，失败/跳过 {len(failed)} 条",
    )
    return success(result.model_dump(mode="json"))


@router.post("/batch/assign", summary="批量分配任务负责人")
async def batch_assign(
    body: TaskBatchAssignRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    if not body.assignee_id and not body.assignee_name:
        raise BizException(code=4000, message="需提供 assignee_id 或 assignee_name")
    async with session.begin():
        succeeded, failed = await task_service.batch_assign(
            session,
            body.task_ids,
            operator_id=current_user.id,
            assignee_id=body.assignee_id,
            assignee_name=body.assignee_name,
            comment=body.comment,
            is_manager=is_manager_or_admin(current_user),
        )
    result = TaskBatchResult(
        succeeded=succeeded,
        failed=failed,
        message=f"成功分配 {len(succeeded)} 条，失败/跳过 {len(failed)} 条",
    )
    return success(result.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# 静态子路径（放在 {task_id} 动态路由之前）
# ---------------------------------------------------------------------------

@router.get("/pending-review", summary="待审核任务列表")
async def list_pending_review(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_app_roles("manager", "admin")),
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


# ---------------------------------------------------------------------------
# 动态 {task_id} 路由
# ---------------------------------------------------------------------------

@router.get("/{task_id}", summary="任务详情")
async def get_task_detail(
    task_id: int = Path(..., ge=1),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    task = await task_service.get_task(session, task_id)
    if task is None:
        raise BizException(code=4044, message=f"任务 id={task_id} 不存在")
    _ensure_task_visible(task, current_user)
    return success(TaskDetail.model_validate(task).model_dump(mode="json"))


@router.get("", summary="任务列表（支持高级筛选）")
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    assignee_id: Optional[int] = Query(default=None, ge=1),
    status: Optional[str] = Query(default=None),
    risk_level: Optional[str] = Query(default=None),
    task_type: Optional[str] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    due_before: Optional[datetime] = Query(default=None),
    due_after: Optional[datetime] = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    effective_assignee_id = assignee_id
    if not is_manager_or_admin(current_user):
        if assignee_id is not None and assignee_id != current_user.id:
            raise BizException(code=4030, message="当前账号无权查看其他负责人的任务")
        effective_assignee_id = current_user.id

    items, total = await task_service.list_tasks(
        session,
        page=page,
        page_size=page_size,
        assignee_id=effective_assignee_id,
        status=status,
        risk_level=risk_level,
        task_type=task_type,
        priority=priority,
        due_before=due_before,
        due_after=due_after,
    )
    resp = TaskListResponse(
        items=[TaskListItem.model_validate(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
    )
    return success(resp.model_dump(mode="json"))


@router.post("/{task_id}/review", summary="人工审核决策")
async def review_task(
    task_id: int = Path(..., ge=1),
    body: TaskReviewRequest = ...,
    current_user: CurrentUser = Depends(require_app_roles("manager", "admin")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    body.reviewer_id = current_user.id
    async with session.begin():
        result = await task_service.review_task(session, task_id, body)
    return success(result.model_dump(mode="json"))


@router.post("/{task_id}/remind", summary="设置/更新任务提醒")
async def set_remind(
    task_id: int = Path(..., ge=1),
    body: TaskRemindRequest = ...,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
    redis: Redis = Depends(redis_client),
) -> dict:
    async with session.begin():
        task = await task_service.get_task(session, task_id)
        if task is None:
            raise BizException(code=4044, message=f"任务 id={task_id} 不存在")
        _ensure_task_handler(task, current_user)
        task.remind_at = body.remind_at
        if body.due_at is not None:
            task.due_at = body.due_at
        await session.flush()
        await session.refresh(task)

    await schedule_reminder(redis, task_id, body.remind_at)
    if body.due_at is not None:
        await schedule_deadline(redis, task_id, body.due_at)

    return success(TaskRemindResult(
        task_id=task_id,
        remind_at=body.remind_at,
        due_at=body.due_at,
        message="提醒已设置",
    ).model_dump(mode="json"))


@router.delete("/{task_id}/remind", summary="取消任务提醒")
async def cancel_remind(
    task_id: int = Path(..., ge=1),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
    redis: Redis = Depends(redis_client),
) -> dict:
    async with session.begin():
        task = await task_service.get_task(session, task_id)
        if task is None:
            raise BizException(code=4044, message=f"任务 id={task_id} 不存在")
        _ensure_task_handler(task, current_user)

    await cancel_reminder(redis, task_id)
    await cancel_deadline(redis, task_id)
    return success({"task_id": task_id, "message": "提醒已取消"})


@router.patch("/{task_id}/complete", summary="完成任务")
async def complete_task(
    task_id: int = Path(..., ge=1),
    body: TaskCompleteRequest = ...,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
    redis: Redis = Depends(redis_client),
) -> dict:
    async with session.begin():
        existing = await task_service.get_task(session, task_id)
        if existing is None:
            raise BizException(code=4044, message=f"任务 id={task_id} 不存在")
        _ensure_task_handler(existing, current_user)
        task = await task_service.complete_task(
            session, task_id,
            operator_id=current_user.id,
            comment=body.comment,
        )
    await cancel_reminder(redis, task_id)
    await cancel_deadline(redis, task_id)
    return success(TaskDetail.model_validate(task).model_dump(mode="json"))


@router.patch("/{task_id}/cancel", summary="取消任务")
async def cancel_task(
    task_id: int = Path(..., ge=1),
    body: TaskCancelRequest = ...,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
    redis: Redis = Depends(redis_client),
) -> dict:
    async with session.begin():
        existing = await task_service.get_task(session, task_id)
        if existing is None:
            raise BizException(code=4044, message=f"任务 id={task_id} 不存在")
        _ensure_task_owner_or_manager(existing, current_user)
        task = await task_service.cancel_task(
            session, task_id,
            operator_id=current_user.id,
            reason=body.reason,
        )
    await cancel_reminder(redis, task_id)
    await cancel_deadline(redis, task_id)
    return success(TaskDetail.model_validate(task).model_dump(mode="json"))


@router.patch("/{task_id}/assign", summary="重新分配任务负责人")
async def assign_task(
    task_id: int = Path(..., ge=1),
    body: TaskAssignRequest = ...,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    async with session.begin():
        existing = await task_service.get_task(session, task_id)
        if existing is None:
            raise BizException(code=4044, message=f"任务 id={task_id} 不存在")
        _ensure_task_owner_or_manager(existing, current_user)
        task = await task_service.assign_task(
            session, task_id,
            assignee_id=body.assignee_id,
            assignee_name=body.assignee_name,
            operator_id=current_user.id,
            comment=body.comment,
        )
    return success(TaskDetail.model_validate(task).model_dump(mode="json"))


@router.get("/{task_id}/timeline", summary="任务事件时间线")
async def get_timeline(
    task_id: int = Path(..., ge=1),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    task = await task_service.get_task(session, task_id)
    if task is None:
        raise BizException(code=4044, message=f"任务 id={task_id} 不存在")
    _ensure_task_visible(task, current_user)
    items, total = await task_service.list_timeline(session, task_id)
    resp = TaskTimelineResponse(
        items=[TaskEventOut.model_validate(ev) for ev in items],
        total=total,
    )
    return success(resp.model_dump(mode="json"))


@router.post("/{task_id}/comments", summary="添加评论")
async def add_comment(
    task_id: int = Path(..., ge=1),
    body: TaskCommentRequest = ...,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    async with session.begin():
        task = await task_service.get_task(session, task_id)
        if task is None:
            raise BizException(code=4044, message=f"任务 id={task_id} 不存在")
        _ensure_task_visible(task, current_user)
        event = await task_service.add_comment(
            session, task_id,
            operator_id=current_user.id,
            content=body.content,
        )
    return success(TaskCommentOut(
        id=event.id,
        task_id=event.task_id,
        operator_id=event.operator_id,
        operator_kind=event.operator_kind,
        content=(event.payload or {}).get("content", ""),
        created_at=event.created_at,
    ).model_dump(mode="json"))


@router.post("/{task_id}/attachments", summary="记录附件元数据")
async def add_attachment(
    task_id: int = Path(..., ge=1),
    body: TaskAttachmentRequest = ...,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    async with session.begin():
        task = await task_service.get_task(session, task_id)
        if task is None:
            raise BizException(code=4044, message=f"任务 id={task_id} 不存在")
        _ensure_task_visible(task, current_user)
        event = await task_service.add_attachment(
            session, task_id,
            operator_id=current_user.id,
            name=body.name,
            url=body.url,
            size=body.size,
        )
    return success({
        "id": event.id,
        "task_id": event.task_id,
        "name": body.name,
        "url": body.url,
        "size": body.size,
        "operator_id": event.operator_id,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    })


@router.patch("/{task_id}/collaborators", summary="更新协作者列表")
async def update_collaborators(
    task_id: int = Path(..., ge=1),
    body: TaskCollaboratorRequest = ...,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    async with session.begin():
        task = await task_service.get_task(session, task_id)
        if task is None:
            raise BizException(code=4044, message=f"任务 id={task_id} 不存在")
        _ensure_task_owner_or_manager(task, current_user)
        task = await task_service.update_collaborators(
            session, task_id,
            user_ids=body.user_ids,
            operator_id=current_user.id,
        )
    return success(TaskDetail.model_validate(task).model_dump(mode="json"))
