"""任务服务层：任务持久化 + 事件流写入。

关键设计：
- create_from_draft 是 Agent 落库入口，单事务内同时写入 tasks + task_events。
- 名称解析（hospital_name/product_name/assignee_name）在此处完成，
  避免污染 Agent 节点。
- 不在此处做风险判定（留给 Risk Agent / Phase 5）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizException
from app.core.logger import get_logger
from app.models.enums import (
    BusinessObjectType,
    ReviewStatus,
    RiskLevel,
    TaskEventType,
    TaskPriority,
    TaskStatus,
    TaskType,
)
from app.models.hospital import Hospital
from app.models.product import Product
from app.models.task import Task
from app.models.task_event import TaskEvent
from app.services.user_service import find_user_by_name, get_default_user, get_user_by_id
from app.schemas.task import TaskDraft

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
    "datetime",
]
