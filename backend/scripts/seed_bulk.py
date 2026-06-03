"""批量灌入开发库虚拟数据：每张业务表补齐到 N 条（默认 50）。

运行（在 backend/ 目录，已激活虚拟环境）：

    python -m scripts.seed_bulk
    python -m scripts.seed_bulk --count 50
    python -m scripts.seed_bulk --reset          # 先删 DEMO_ 前缀数据再重灌
    python -m scripts.seed_bulk --reset --count 100

说明：
- 内置角色/员工/医院/产品（张客服等）会保留；不足 N 条时用 DEMO_ 前缀记录补齐。
- roles 表：7 个业务角色 + DEMO_ROLE_xxx 虚拟角色，合计 N 条。
- 子表（tasks / events / risk_records 等）同样补齐到 N 条，且彼此外键关联正确。
- 幂等：不加 --reset 时，已够 N 条则跳过该表。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Sequence

from sqlalchemy import delete, func, select

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.db import AsyncSessionLocal  # noqa: E402
from app.core.logger import get_logger, setup_logging  # noqa: E402
from app.models.agent_trace import AgentTrace  # noqa: E402
from app.models.enums import (  # noqa: E402
    AgentNode,
    AgentTraceStatus,
    BusinessObjectType,
    KnowledgeGapStatus,
    NotificationChannel,
    NotificationKind,
    NotificationStatus,
    ReviewStatus,
    RiskLevel,
    RoleCode,
    TaskEventType,
    TaskPriority,
    TaskStatus,
    TaskType,
)
from app.models.hospital import Hospital  # noqa: E402
from app.models.knowledge_gap import KnowledgeGapTask  # noqa: E402
from app.models.notification import Notification  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.models.risk_record import RiskRecord  # noqa: E402
from app.models.task import Task  # noqa: E402
from app.models.task_event import TaskEvent  # noqa: E402
from app.models.user import Role, User, UserRole  # noqa: E402
from scripts.seed_data import (  # noqa: E402
    BUSINESS_UNITS,
    DEPARTMENTS,
    HOSPITALS,
    HOSPITAL_LEVELS,
    PRODUCTS,
    PRODUCT_CATEGORIES,
    REGIONS,
    ROLES,
    USERS,
)

logger = get_logger("seed_bulk")

DEMO_PREFIX = "DEMO_"


async def _active_count(session, model) -> int:
    q = select(func.count()).select_from(model).where(model.deleted_at.is_(None))
    return int((await session.execute(q)).scalar_one())


async def _reset_demo(session) -> None:
    """按外键顺序删除 DEMO_ 前缀及 demo- trace 相关数据。"""
    demo_users = select(User.id).where(
        User.employee_no.like(f"{DEMO_PREFIX}%"), User.deleted_at.is_(None)
    )
    demo_tasks = select(Task.id).where(Task.trace_id.like("demo-%"))

    await session.execute(
        delete(AgentTrace).where(AgentTrace.trace_id.like("demo-%"))
    )
    await session.execute(
        delete(Notification).where(Notification.trace_id.like("demo-%"))
    )
    await session.execute(
        delete(KnowledgeGapTask).where(KnowledgeGapTask.trace_id.like("demo-%"))
    )
    await session.execute(delete(TaskEvent).where(TaskEvent.task_id.in_(demo_tasks)))
    await session.execute(delete(RiskRecord).where(RiskRecord.task_id.in_(demo_tasks)))
    await session.execute(delete(Notification).where(Notification.task_id.in_(demo_tasks)))
    await session.execute(
        delete(KnowledgeGapTask).where(KnowledgeGapTask.source_task_id.in_(demo_tasks))
    )
    await session.execute(delete(Task).where(Task.trace_id.like("demo-%")))
    await session.execute(delete(UserRole).where(UserRole.user_id.in_(demo_users)))
    await session.execute(
        delete(User).where(User.employee_no.like(f"{DEMO_PREFIX}%"))
    )
    await session.execute(
        delete(Hospital).where(Hospital.code.like(f"{DEMO_PREFIX}%"))
    )
    await session.execute(
        delete(Product).where(Product.code.like(f"{DEMO_PREFIX}%"))
    )
    await session.execute(
        delete(Role).where(Role.code.like("demo_role_%"))
    )
    logger.info("demo data cleared (DEMO_ / demo- trace)")


async def _ensure_canonical_roles(session) -> dict[str, Role]:
    code_to_role: dict[str, Role] = {}
    for spec in ROLES:
        code = spec["code"].value if hasattr(spec["code"], "value") else spec["code"]
        existing = (
            await session.execute(select(Role).where(Role.code == code))
        ).scalar_one_or_none()
        if existing:
            code_to_role[code] = existing
            continue
        role = Role(code=code, name=spec["name"], description=spec["description"])
        session.add(role)
        await session.flush()
        code_to_role[code] = role
    return code_to_role


async def _top_up_roles(session, target: int) -> list[Role]:
    await _ensure_canonical_roles(session)
    roles = (
        (await session.execute(select(Role).where(Role.deleted_at.is_(None))))
        .scalars()
        .all()
    )
    need = target - len(roles)
    for i in range(need):
        idx = len(roles) + i + 1
        code = f"demo_role_{idx:03d}"
        if (
            await session.execute(select(Role).where(Role.code == code))
        ).scalar_one_or_none():
            continue
        role = Role(
            code=code,
            name=f"虚拟角色{idx:03d}",
            description="批量灌库生成的演示角色",
        )
        session.add(role)
        await session.flush()
        roles.append(role)
    await session.flush()
    return list(
        (await session.execute(select(Role).where(Role.deleted_at.is_(None)).limit(target)))
        .scalars()
        .all()
    )[:target]


async def _top_up_users(session, roles: Sequence[Role], target: int) -> list[User]:
    code_to_role = {r.code: r for r in roles}
    role_codes = [rc.value for rc in RoleCode]

    # 内置员工
    for spec in USERS:
        existing = (
            await session.execute(
                select(User).where(User.employee_no == spec["employee_no"])
            )
        ).scalar_one_or_none()
        if existing:
            user = existing
        else:
            user = User(
                employee_no=spec["employee_no"],
                name=spec["name"],
                email=spec["email"],
                department=spec["department"],
                is_active=True,
            )
            session.add(user)
            await session.flush()
        for role_code in spec["roles"]:
            code = role_code.value if hasattr(role_code, "value") else role_code
            role = code_to_role.get(code)
            if role is None:
                continue
            link = (
                await session.execute(
                    select(UserRole).where(
                        UserRole.user_id == user.id, UserRole.role_id == role.id
                    )
                )
            ).scalar_one_or_none()
            if not link:
                session.add(UserRole(user_id=user.id, role_id=role.id))

    users = (
        (await session.execute(select(User).where(User.deleted_at.is_(None))))
        .scalars()
        .all()
    )
    need = target - len(users)
    for i in range(need):
        n = len(users) + i + 1
        emp = f"{DEMO_PREFIX}E{n:04d}"
        if (
            await session.execute(select(User).where(User.employee_no == emp))
        ).scalar_one_or_none():
            continue
        dept = DEPARTMENTS[n % len(DEPARTMENTS)]
        user = User(
            employee_no=emp,
            name=f"虚拟员工{n:03d}",
            email=f"demo{n:03d}@example.com",
            phone=f"138{n:08d}"[:11],
            wxwork_userid=f"wx_demo_{n:04d}",
            department=dept,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        role = code_to_role.get(role_codes[n % len(role_codes)])
        if role:
            session.add(UserRole(user_id=user.id, role_id=role.id))
        users.append(user)

    await session.flush()
    return list(
        (await session.execute(select(User).where(User.deleted_at.is_(None)).limit(target)))
        .scalars()
        .all()
    )[:target]


async def _top_up_user_roles(session, users: Sequence[User], roles: Sequence[Role], target: int) -> None:
    current = await _active_count(session, UserRole)
    if current >= target:
        return
    role_list = list(roles)
    for i in range(current, target):
        user = users[i % len(users)]
        role = role_list[i % len(role_list)]
        exists = (
            await session.execute(
                select(UserRole).where(
                    UserRole.user_id == user.id, UserRole.role_id == role.id
                )
            )
        ).scalar_one_or_none()
        if not exists:
            session.add(UserRole(user_id=user.id, role_id=role.id))


async def _top_up_hospitals(session, target: int) -> list[Hospital]:
    for spec in HOSPITALS:
        if (
            await session.execute(select(Hospital).where(Hospital.code == spec["code"]))
        ).scalar_one_or_none():
            continue
        session.add(Hospital(**spec))

    hospitals = (
        (await session.execute(select(Hospital).where(Hospital.deleted_at.is_(None))))
        .scalars()
        .all()
    )
    need = target - len(hospitals)
    for i in range(need):
        n = len(hospitals) + i + 1
        code = f"{DEMO_PREFIX}H{n:04d}"
        if (
            await session.execute(select(Hospital).where(Hospital.code == code))
        ).scalar_one_or_none():
            continue
        session.add(
            Hospital(
                code=code,
                name=f"虚拟医院{n:03d}",
                level=HOSPITAL_LEVELS[n % len(HOSPITAL_LEVELS)],
                region=REGIONS[n % len(REGIONS)],
                risk_score=(n * 7) % 100,
                contact_name=f"联系人{n:03d}",
                contact_phone=f"139{n:08d}"[:11],
            )
        )

    await session.flush()
    return list(
        (
            await session.execute(
                select(Hospital).where(Hospital.deleted_at.is_(None)).limit(target)
            )
        )
        .scalars()
        .all()
    )[:target]


async def _top_up_products(session, target: int) -> list[Product]:
    for spec in PRODUCTS:
        if (
            await session.execute(select(Product).where(Product.code == spec["code"]))
        ).scalar_one_or_none():
            continue
        session.add(Product(**spec))

    products = (
        (await session.execute(select(Product).where(Product.deleted_at.is_(None))))
        .scalars()
        .all()
    )
    need = target - len(products)
    for i in range(need):
        n = len(products) + i + 1
        code = f"{DEMO_PREFIX}P{n:04d}"
        if (
            await session.execute(select(Product).where(Product.code == code))
        ).scalar_one_or_none():
            continue
        session.add(
            Product(
                code=code,
                name=f"虚拟产品{n:03d}",
                category=PRODUCT_CATEGORIES[n % len(PRODUCT_CATEGORIES)],
                business_unit=BUSINESS_UNITS[n % len(BUSINESS_UNITS)],
                description=f"演示产品 {n} 的说明",
            )
        )
    await session.flush()
    return list(
        (
            await session.execute(
                select(Product).where(Product.deleted_at.is_(None)).limit(target)
            )
        )
        .scalars()
        .all()
    )[:target]


def _pick_enum(values: list, index: int):
    return values[index % len(values)]


async def _top_up_tasks(
    session,
    users: Sequence[User],
    hospitals: Sequence[Hospital],
    products: Sequence[Product],
    target: int,
) -> list[Task]:
    existing = await _active_count(session, Task)
    if existing >= target:
        return list(
            (await session.execute(select(Task).where(Task.deleted_at.is_(None)).limit(target)))
            .scalars()
            .all()
        )[:target]

    task_types = list(TaskType)
    statuses = list(TaskStatus)
    priorities = list(TaskPriority)
    risk_levels = list(RiskLevel)
    biz_types = list(BusinessObjectType)
    now = datetime.now().replace(microsecond=0)

    tasks: list[Task] = []
    for i in range(existing, target):
        n = i + 1
        trace_id = f"demo-trace-{n:04d}"
        if (
            await session.execute(select(Task).where(Task.trace_id == trace_id))
        ).scalar_one_or_none():
            continue

        ttype = _pick_enum(task_types, i)
        status = _pick_enum(statuses, i)
        priority = _pick_enum(priorities, i)
        risk = _pick_enum(risk_levels, i)
        assignee = users[i % len(users)]
        creator = users[(i + 1) % len(users)]
        hospital = hospitals[i % len(hospitals)] if hospitals else None
        product = products[i % len(products)] if products else None

        review = ReviewStatus.NONE.value
        reviewer_id = None
        reviewed_at = None
        review_comment = None
        if risk in (RiskLevel.HIGH.value, RiskLevel.CRITICAL.value):
            status = TaskStatus.AWAITING_REVIEW.value
            review = ReviewStatus.PENDING.value
        if status == TaskStatus.COMPLETED.value:
            completed_at = now - timedelta(days=i % 10)
        else:
            completed_at = None

        task = Task(
            type=ttype.value,
            title=f"[演示] 任务{n:03d} - {ttype.value}",
            description=f"这是第 {n} 条标准虚拟任务，用于前端列表/详情/筛选联调。",
            source="seed_bulk" if i % 2 else "agent",
            status=status,
            priority=priority.value,
            assignee_id=assignee.id,
            created_by=creator.id,
            collaborators=[users[(i + 2) % len(users)].id] if len(users) > 2 else None,
            hospital_id=hospital.id if hospital else None,
            product_id=product.id if product else None,
            business_object_type=_pick_enum(biz_types, i).value,
            business_object_id=f"BO-{n:05d}" if i % 3 else None,
            remind_at=now + timedelta(days=i % 14, hours=i % 8),
            due_at=now + timedelta(days=(i % 14) + 3),
            completed_at=completed_at,
            risk_level=risk.value,
            risk_reason=f"演示风险原因 #{n}",
            risk_suggested_action="请在 24 小时内跟进并记录处理结果。",
            review_status=review,
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
            review_comment=review_comment,
            trace_id=trace_id,
            agent_session_id=f"demo-session-{n % 10:02d}",
            extra={"tags": ["demo", "bulk"], "seed_index": n},
        )
        session.add(task)
        tasks.append(task)

    await session.flush()
    return list(
        (await session.execute(select(Task).where(Task.deleted_at.is_(None)).limit(target)))
        .scalars()
        .all()
    )[:target]


async def _top_up_task_events(session, tasks: Sequence[Task], users: Sequence[User], target: int) -> None:
    current = await _active_count(session, TaskEvent)
    need = target - current
    if need <= 0:
        return
    event_types = list(TaskEventType)
    for i in range(need):
        task = tasks[i % len(tasks)]
        etype = _pick_enum(event_types, i)
        session.add(
            TaskEvent(
                task_id=task.id,
                event_type=etype.value,
                operator_id=users[i % len(users)].id if etype != TaskEventType.CREATE else None,
                operator_kind="agent" if i % 2 == 0 else "user",
                payload={"demo": True, "index": i + 1, "note": f"事件 {etype.value}"},
                trace_id=task.trace_id,
            )
        )


async def _top_up_risk_records(session, tasks: Sequence[Task], target: int) -> None:
    current = await _active_count(session, RiskRecord)
    need = target - current
    for i in range(need):
        task = tasks[i % len(tasks)]
        review = (
            ReviewStatus.PENDING.value
            if task.risk_level in (RiskLevel.HIGH.value, RiskLevel.CRITICAL.value)
            else ReviewStatus.NONE.value
        )
        session.add(
            RiskRecord(
                task_id=task.id,
                risk_level=task.risk_level,
                reason=task.risk_reason,
                suggested_action=task.risk_suggested_action,
                keywords_hit=["演示", "虚拟"] if i % 2 == 0 else [],
                rule_hit=[f"rule_demo_{i % 5}"],
                llm_judgement={
                    "level": task.risk_level,
                    "confidence": 0.75 + (i % 20) * 0.01,
                    "signals": ["demo"],
                },
                review_status=review,
                trace_id=task.trace_id,
            )
        )


async def _top_up_knowledge_gaps(session, tasks: Sequence[Task], users: Sequence[User], target: int) -> None:
    current = await _active_count(session, KnowledgeGapTask)
    need = target - current
    statuses = list(KnowledgeGapStatus)
    for i in range(need):
        task = tasks[i % len(tasks)]
        session.add(
            KnowledgeGapTask(
                source_task_id=task.id,
                original_question=f"关于任务 {task.id} 的 SOP 未找到，如何标准处理？",
                retrieval_query=f"SOP {task.type} 处理流程",
                confidence=0.2 + (i % 50) * 0.01,
                rag_hits_snapshot=[
                    {"doc_id": f"doc-{i}", "score": 0.3, "snippet": "相关片段…"}
                ],
                assignee_id=users[i % len(users)].id,
                status=_pick_enum(statuses, i).value,
                resolution_note="已补充文档链接" if i % 4 == 0 else None,
                trace_id=task.trace_id,
            )
        )


async def _top_up_notifications(session, tasks: Sequence[Task], users: Sequence[User], target: int) -> None:
    current = await _active_count(session, Notification)
    need = target - current
    kinds = list(NotificationKind)
    channels = list(NotificationChannel)
    statuses = list(NotificationStatus)
    now = datetime.now()
    for i in range(need):
        task = tasks[i % len(tasks)]
        user = users[i % len(users)]
        st = _pick_enum(statuses, i)
        session.add(
            Notification(
                task_id=task.id,
                kind=_pick_enum(kinds, i).value,
                channel=_pick_enum(channels, i).value,
                recipient_user_id=user.id,
                recipient_address=user.email or user.wxwork_userid,
                title=f"[通知] 任务 {task.id}",
                content=f"演示通知内容 #{i + 1}",
                payload={"template": "demo", "task_id": task.id},
                status=st.value,
                retry_count=i % 3,
                sent_at=now - timedelta(hours=i) if st == NotificationStatus.SENT else None,
                error_message="模拟发送失败" if st == NotificationStatus.FAILED else None,
                trace_id=task.trace_id,
            )
        )


async def _top_up_agent_traces(session, tasks: Sequence[Task], target: int) -> None:
    current = await _active_count(session, AgentTrace)
    need = target - current
    nodes = list(AgentNode)
    statuses = list(AgentTraceStatus)
    for i in range(need):
        task = tasks[i % len(tasks)] if tasks else None
        trace_id = task.trace_id if task else f"demo-trace-orphan-{i:04d}"
        session.add(
            AgentTrace(
                trace_id=trace_id,
                session_id=task.agent_session_id if task else f"demo-session-{i % 10}",
                node=_pick_enum(nodes, i).value,
                status=_pick_enum(statuses, i).value,
                input_data={"user_input": f"演示输入 {i}"},
                output_data={"ok": True, "index": i},
                tool_name="mock_tool" if i % 5 == 0 else None,
                duration_ms=100 + i * 10,
                retry_count=i % 2,
                error_message="模拟节点错误" if i % 17 == 0 else None,
            )
        )


async def run_seed(count: int, reset: bool) -> None:
    setup_logging()
    async with AsyncSessionLocal() as session:
        async with session.begin():
            if reset:
                await _reset_demo(session)

            roles = await _top_up_roles(session, count)
            users = await _top_up_users(session, roles, count)
            await _top_up_user_roles(session, users, roles, count)
            hospitals = await _top_up_hospitals(session, count)
            products = await _top_up_products(session, count)
            tasks = await _top_up_tasks(session, users, hospitals, products, count)
            await _top_up_task_events(session, tasks, users, count)
            await _top_up_risk_records(session, tasks, count)
            await _top_up_knowledge_gaps(session, tasks, users, count)
            await _top_up_notifications(session, tasks, users, count)
            await _top_up_agent_traces(session, tasks, count)

    # 打印汇总
    async with AsyncSessionLocal() as session:
        tables = [
            ("roles", Role),
            ("users", User),
            ("user_roles", UserRole),
            ("hospitals", Hospital),
            ("products", Product),
            ("tasks", Task),
            ("task_events", TaskEvent),
            ("risk_records", RiskRecord),
            ("knowledge_gap_tasks", KnowledgeGapTask),
            ("notifications", Notification),
            ("agent_traces", AgentTrace),
        ]
        for name, model in tables:
            n = await _active_count(session, model)
            logger.info("table %-22s -> %s rows", name, n)

    logger.info("seed_bulk completed (target=%s, reset=%s).", count, reset)


def main() -> None:
    parser = argparse.ArgumentParser(description="批量灌入每张表 N 条虚拟数据")
    parser.add_argument("--count", type=int, default=50, help="每张表目标行数（默认 50）")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="先删除 DEMO_ 前缀 / demo- trace 数据再重灌",
    )
    args = parser.parse_args()
    if args.count < 1:
        raise SystemExit("--count 必须 >= 1")
    asyncio.run(run_seed(args.count, args.reset))


if __name__ == "__main__":
    main()
