"""任务接口。

骨架已实现：
- GET /tasks/{task_id}: 任务详情
- GET /tasks: 任务列表（按 assignee_id / status / risk_level 过滤，分页）

后续将补充：
- POST /tasks: 结构化创建（与 /agent/chat 互补，前端表单走这里）
- PATCH /tasks/{id} / complete / cancel / assign
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.core.exceptions import BizException
from app.core.response import success
from app.schemas.task import TaskDetail, TaskListItem, TaskListResponse
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


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
