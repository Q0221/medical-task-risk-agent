"""业务档案服务层。

提供医院档案和产品档案的列表查询、详情查询和总览统计。
所有涉及任务统计的查询均通过子查询一次完成，避免 N+1 查询。
"""

from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RiskLevel, TaskStatus
from app.models.hospital import Hospital
from app.models.product import Product
from app.models.task import Task

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_OPEN_STATUSES = (
    TaskStatus.PENDING.value,
    TaskStatus.IN_PROGRESS.value,
    TaskStatus.BLOCKED.value,
    TaskStatus.AWAITING_REVIEW.value,
)
_HIGH_RISK_LEVELS = (RiskLevel.HIGH.value, RiskLevel.CRITICAL.value)


# ---------------------------------------------------------------------------
# 内部工具：构造任务统计子查询
# ---------------------------------------------------------------------------

def _hospital_task_stats_subquery():
    """按 hospital_id 汇总任务数量的子查询。"""
    return (
        select(
            Task.hospital_id,
            func.count(Task.id).label("task_total"),
            func.sum(
                case((Task.status.in_(_OPEN_STATUSES), 1), else_=0)
            ).label("task_open"),
            func.sum(
                case((Task.risk_level.in_(_HIGH_RISK_LEVELS), 1), else_=0)
            ).label("task_high_risk"),
            func.max(Task.created_at).label("latest_task_at"),
        )
        .where(Task.deleted_at.is_(None), Task.hospital_id.isnot(None))
        .group_by(Task.hospital_id)
        .subquery()
    )


def _product_task_stats_subquery():
    """按 product_id 汇总任务数量的子查询。"""
    return (
        select(
            Task.product_id,
            func.count(Task.id).label("task_total"),
            func.sum(
                case((Task.status.in_(_OPEN_STATUSES), 1), else_=0)
            ).label("task_open"),
            func.sum(
                case((Task.risk_level.in_(_HIGH_RISK_LEVELS), 1), else_=0)
            ).label("task_high_risk"),
            func.max(Task.created_at).label("latest_task_at"),
        )
        .where(Task.deleted_at.is_(None), Task.product_id.isnot(None))
        .group_by(Task.product_id)
        .subquery()
    )


# ---------------------------------------------------------------------------
# 档案总览统计
# ---------------------------------------------------------------------------

async def get_record_stats(session: AsyncSession) -> dict:
    """返回档案页顶部四个统计数字。"""
    hospital_count = (
        await session.execute(
            select(func.count(Hospital.id)).where(Hospital.deleted_at.is_(None))
        )
    ).scalar_one()

    product_count = (
        await session.execute(
            select(func.count(Product.id)).where(Product.deleted_at.is_(None))
        )
    ).scalar_one()

    risk_task_count = (
        await session.execute(
            select(func.count(Task.id)).where(
                Task.deleted_at.is_(None),
                Task.risk_level.in_(_HIGH_RISK_LEVELS),
            )
        )
    ).scalar_one()

    high_risk_hospital_count = (
        await session.execute(
            select(func.count(Hospital.id)).where(
                Hospital.deleted_at.is_(None),
                Hospital.risk_score > 0,
            )
        )
    ).scalar_one()

    open_task_count = (
        await session.execute(
            select(func.count(Task.id)).where(
                Task.deleted_at.is_(None),
                Task.status.in_(_OPEN_STATUSES),
            )
        )
    ).scalar_one()

    return {
        "hospital_count": hospital_count,
        "product_count": product_count,
        "risk_task_count": risk_task_count,
        "high_risk_hospital_count": high_risk_hospital_count,
        "open_task_count": open_task_count,
    }


# ---------------------------------------------------------------------------
# 医院档案查询
# ---------------------------------------------------------------------------

async def list_hospitals(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    level: Optional[str] = None,
    region: Optional[str] = None,
) -> tuple[list[dict], int]:
    """分页查询医院列表，附带任务统计聚合。

    返回 (rows, total)，每个 row 是包含医院字段和聚合字段的 dict。
    """
    stats_sq = _hospital_task_stats_subquery()

    base_stmt = (
        select(
            Hospital,
            func.coalesce(stats_sq.c.task_total, 0).label("task_total"),
            func.coalesce(stats_sq.c.task_open, 0).label("task_open"),
            func.coalesce(stats_sq.c.task_high_risk, 0).label("task_high_risk"),
            stats_sq.c.latest_task_at,
        )
        .outerjoin(stats_sq, Hospital.id == stats_sq.c.hospital_id)
        .where(Hospital.deleted_at.is_(None))
    )

    if search:
        keyword = f"%{search.strip()}%"
        base_stmt = base_stmt.where(
            Hospital.name.like(keyword) | Hospital.region.like(keyword)
        )
    if level:
        base_stmt = base_stmt.where(Hospital.level == level)
    if region:
        base_stmt = base_stmt.where(Hospital.region == region)

    # 计算总数
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    # 分页排序：风险分降序，再按 ID 升序保证稳定
    data_stmt = (
        base_stmt
        .order_by(Hospital.risk_score.desc(), Hospital.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await session.execute(data_stmt)).all()

    result = []
    for row in rows:
        hospital: Hospital = row[0]
        item = {
            "id": hospital.id,
            "code": hospital.code,
            "name": hospital.name,
            "level": hospital.level,
            "region": hospital.region,
            "risk_score": hospital.risk_score,
            "contact_name": hospital.contact_name,
            "contact_phone": hospital.contact_phone,
            "task_total": row.task_total,
            "task_open": row.task_open,
            "task_high_risk": row.task_high_risk,
            "latest_task_at": row.latest_task_at,
            "updated_at": hospital.updated_at,
        }
        result.append(item)

    return result, total


async def get_hospital_detail(
    session: AsyncSession, hospital_id: int
) -> Optional[dict]:
    """获取单个医院详情，附带近 10 条任务和关联产品名称列表。"""
    stats_sq = _hospital_task_stats_subquery()

    stmt = (
        select(
            Hospital,
            func.coalesce(stats_sq.c.task_total, 0).label("task_total"),
            func.coalesce(stats_sq.c.task_open, 0).label("task_open"),
            func.coalesce(stats_sq.c.task_high_risk, 0).label("task_high_risk"),
            stats_sq.c.latest_task_at,
        )
        .outerjoin(stats_sq, Hospital.id == stats_sq.c.hospital_id)
        .where(Hospital.id == hospital_id, Hospital.deleted_at.is_(None))
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None

    hospital: Hospital = row[0]

    # 近 10 条任务（按创建时间倒序）
    recent_tasks_rows = (
        await session.execute(
            select(Task)
            .where(Task.hospital_id == hospital_id, Task.deleted_at.is_(None))
            .order_by(Task.created_at.desc())
            .limit(10)
        )
    ).scalars().all()

    # 关联产品名称（去重）
    product_ids = list({t.product_id for t in recent_tasks_rows if t.product_id})
    related_products: list[str] = []
    if product_ids:
        products = (
            await session.execute(
                select(Product.name)
                .where(Product.id.in_(product_ids), Product.deleted_at.is_(None))
            )
        ).scalars().all()
        related_products = list(products)

    return {
        "id": hospital.id,
        "code": hospital.code,
        "name": hospital.name,
        "level": hospital.level,
        "region": hospital.region,
        "risk_score": hospital.risk_score,
        "contact_name": hospital.contact_name,
        "contact_phone": hospital.contact_phone,
        "task_total": row.task_total,
        "task_open": row.task_open,
        "task_high_risk": row.task_high_risk,
        "latest_task_at": row.latest_task_at,
        "updated_at": hospital.updated_at,
        "recent_tasks": [
            {
                "id": t.id,
                "title": t.title,
                "type": t.type,
                "status": t.status,
                "risk_level": t.risk_level,
                "priority": t.priority,
                "assignee_id": t.assignee_id,
                "due_at": t.due_at,
                "created_at": t.created_at,
            }
            for t in recent_tasks_rows
        ],
        "related_products": related_products,
    }


# ---------------------------------------------------------------------------
# 产品档案查询
# ---------------------------------------------------------------------------

async def list_products(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    category: Optional[str] = None,
    business_unit: Optional[str] = None,
) -> tuple[list[dict], int]:
    """分页查询产品列表，附带任务统计聚合。"""
    stats_sq = _product_task_stats_subquery()

    base_stmt = (
        select(
            Product,
            func.coalesce(stats_sq.c.task_total, 0).label("task_total"),
            func.coalesce(stats_sq.c.task_open, 0).label("task_open"),
            func.coalesce(stats_sq.c.task_high_risk, 0).label("task_high_risk"),
            stats_sq.c.latest_task_at,
        )
        .outerjoin(stats_sq, Product.id == stats_sq.c.product_id)
        .where(Product.deleted_at.is_(None))
    )

    if search:
        keyword = f"%{search.strip()}%"
        base_stmt = base_stmt.where(
            Product.name.like(keyword) | Product.category.like(keyword)
        )
    if category:
        base_stmt = base_stmt.where(Product.category == category)
    if business_unit:
        base_stmt = base_stmt.where(Product.business_unit == business_unit)

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    data_stmt = (
        base_stmt
        .order_by(Product.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await session.execute(data_stmt)).all()

    result = []
    for row in rows:
        product: Product = row[0]
        item = {
            "id": product.id,
            "code": product.code,
            "name": product.name,
            "category": product.category,
            "business_unit": product.business_unit,
            "description": product.description,
            "task_total": row.task_total,
            "task_open": row.task_open,
            "task_high_risk": row.task_high_risk,
            "latest_task_at": row.latest_task_at,
            "updated_at": product.updated_at,
        }
        result.append(item)

    return result, total


async def get_product_detail(
    session: AsyncSession, product_id: int
) -> Optional[dict]:
    """获取单个产品详情，附带近 10 条任务和关联医院名称列表。"""
    stats_sq = _product_task_stats_subquery()

    stmt = (
        select(
            Product,
            func.coalesce(stats_sq.c.task_total, 0).label("task_total"),
            func.coalesce(stats_sq.c.task_open, 0).label("task_open"),
            func.coalesce(stats_sq.c.task_high_risk, 0).label("task_high_risk"),
            stats_sq.c.latest_task_at,
        )
        .outerjoin(stats_sq, Product.id == stats_sq.c.product_id)
        .where(Product.id == product_id, Product.deleted_at.is_(None))
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None

    product: Product = row[0]

    recent_tasks_rows = (
        await session.execute(
            select(Task)
            .where(Task.product_id == product_id, Task.deleted_at.is_(None))
            .order_by(Task.created_at.desc())
            .limit(10)
        )
    ).scalars().all()

    # 关联医院名称（去重）
    hospital_ids = list({t.hospital_id for t in recent_tasks_rows if t.hospital_id})
    related_hospitals: list[str] = []
    if hospital_ids:
        hospitals = (
            await session.execute(
                select(Hospital.name)
                .where(Hospital.id.in_(hospital_ids), Hospital.deleted_at.is_(None))
            )
        ).scalars().all()
        related_hospitals = list(hospitals)

    return {
        "id": product.id,
        "code": product.code,
        "name": product.name,
        "category": product.category,
        "business_unit": product.business_unit,
        "description": product.description,
        "task_total": row.task_total,
        "task_open": row.task_open,
        "task_high_risk": row.task_high_risk,
        "latest_task_at": row.latest_task_at,
        "updated_at": product.updated_at,
        "recent_tasks": [
            {
                "id": t.id,
                "title": t.title,
                "type": t.type,
                "status": t.status,
                "risk_level": t.risk_level,
                "priority": t.priority,
                "assignee_id": t.assignee_id,
                "due_at": t.due_at,
                "created_at": t.created_at,
            }
            for t in recent_tasks_rows
        ],
        "related_hospitals": related_hospitals,
    }


# ---------------------------------------------------------------------------
# 筛选选项辅助：获取所有不重复的 level / region / category / business_unit
# ---------------------------------------------------------------------------

async def get_hospital_filter_options(session: AsyncSession) -> dict:
    """返回医院可用的筛选枚举值（level、region）。"""
    levels = (
        await session.execute(
            select(Hospital.level)
            .where(Hospital.deleted_at.is_(None), Hospital.level.isnot(None))
            .distinct()
            .order_by(Hospital.level)
        )
    ).scalars().all()

    regions = (
        await session.execute(
            select(Hospital.region)
            .where(Hospital.deleted_at.is_(None), Hospital.region.isnot(None))
            .distinct()
            .order_by(Hospital.region)
        )
    ).scalars().all()

    return {"levels": list(levels), "regions": list(regions)}


async def get_product_filter_options(session: AsyncSession) -> dict:
    """返回产品可用的筛选枚举值（category、business_unit）。"""
    categories = (
        await session.execute(
            select(Product.category)
            .where(Product.deleted_at.is_(None), Product.category.isnot(None))
            .distinct()
            .order_by(Product.category)
        )
    ).scalars().all()

    units = (
        await session.execute(
            select(Product.business_unit)
            .where(Product.deleted_at.is_(None), Product.business_unit.isnot(None))
            .distinct()
            .order_by(Product.business_unit)
        )
    ).scalars().all()

    return {"categories": list(categories), "business_units": list(units)}
