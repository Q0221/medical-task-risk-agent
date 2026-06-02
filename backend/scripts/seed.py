"""灌入开发期的种子数据：内置角色、示例员工、医院、产品。

运行方式（在 backend/ 目录下）：

    python -m scripts.seed
或
    python scripts/seed.py

幂等：基于唯一键判断已存在则跳过。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.db import AsyncSessionLocal  # noqa: E402
from app.core.logger import get_logger, setup_logging  # noqa: E402
from app.models.enums import RoleCode  # noqa: E402
from app.models.hospital import Hospital  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.models.user import Role, User, UserRole  # noqa: E402

logger = get_logger("seed")


ROLES: list[dict] = [
    {"code": RoleCode.CUSTOMER_SERVICE, "name": "客服", "description": "客户跟进与一线沟通"},
    {"code": RoleCode.MEDICAL_SUPPORT, "name": "医学支持", "description": "医学问题与不良事件处理"},
    {"code": RoleCode.PRODUCT_OPS, "name": "产品运营", "description": "产品反馈与运营"},
    {"code": RoleCode.QA, "name": "质控", "description": "质量控制与复核"},
    {"code": RoleCode.COMPLIANCE, "name": "合规", "description": "合规审核"},
    {"code": RoleCode.MANAGER, "name": "主管", "description": "团队主管 / 审批人"},
    {"code": RoleCode.ADMIN, "name": "系统管理员", "description": "系统管理"},
]

USERS: list[dict] = [
    {
        "employee_no": "E0001",
        "name": "管理员",
        "email": "admin@example.com",
        "department": "IT",
        "roles": [RoleCode.ADMIN],
    },
    {
        "employee_no": "E1001",
        "name": "张客服",
        "email": "zhangcs@example.com",
        "department": "客户服务部",
        "roles": [RoleCode.CUSTOMER_SERVICE],
    },
    {
        "employee_no": "E1002",
        "name": "李医学",
        "email": "limedical@example.com",
        "department": "医学事务部",
        "roles": [RoleCode.MEDICAL_SUPPORT],
    },
    {
        "employee_no": "E1003",
        "name": "王产品",
        "email": "wangpm@example.com",
        "department": "产品部",
        "roles": [RoleCode.PRODUCT_OPS],
    },
    {
        "employee_no": "E1004",
        "name": "赵质控",
        "email": "zhaoqa@example.com",
        "department": "质量管理部",
        "roles": [RoleCode.QA],
    },
    {
        "employee_no": "E1005",
        "name": "钱合规",
        "email": "qiancomp@example.com",
        "department": "合规部",
        "roles": [RoleCode.COMPLIANCE],
    },
    {
        "employee_no": "E2001",
        "name": "孙主管",
        "email": "sunmgr@example.com",
        "department": "客户服务部",
        "roles": [RoleCode.MANAGER],
    },
]

HOSPITALS: list[dict] = [
    {"code": "H001", "name": "示例三甲医院A", "level": "三甲", "region": "华北", "risk_score": 15},
    {"code": "H002", "name": "示例三甲医院B", "level": "三甲", "region": "华东", "risk_score": 35},
    {"code": "H003", "name": "示例二甲医院C", "level": "二甲", "region": "华南", "risk_score": 5},
]

PRODUCTS: list[dict] = [
    {"code": "P001", "name": "示例医疗设备 Alpha", "category": "影像设备", "business_unit": "设备事业部"},
    {"code": "P002", "name": "示例耗材 Beta", "category": "耗材", "business_unit": "耗材事业部"},
    {"code": "P003", "name": "示例软件系统 Gamma", "category": "软件", "business_unit": "软件事业部"},
]


async def _ensure_roles(session) -> dict[str, Role]:
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
        logger.info("created role: %s", code)
    return code_to_role


async def _ensure_users(session, code_to_role: dict[str, Role]) -> None:
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
            logger.info("created user: %s %s", user.employee_no, user.name)

        for role_code in spec["roles"]:
            code = role_code.value if hasattr(role_code, "value") else role_code
            role = code_to_role[code]
            link_exists = (
                await session.execute(
                    select(UserRole).where(
                        UserRole.user_id == user.id, UserRole.role_id == role.id
                    )
                )
            ).scalar_one_or_none()
            if not link_exists:
                session.add(UserRole(user_id=user.id, role_id=role.id))


async def _ensure_hospitals(session) -> None:
    for spec in HOSPITALS:
        existing = (
            await session.execute(select(Hospital).where(Hospital.code == spec["code"]))
        ).scalar_one_or_none()
        if existing:
            continue
        session.add(Hospital(**spec))
        logger.info("created hospital: %s", spec["code"])


async def _ensure_products(session) -> None:
    for spec in PRODUCTS:
        existing = (
            await session.execute(select(Product).where(Product.code == spec["code"]))
        ).scalar_one_or_none()
        if existing:
            continue
        session.add(Product(**spec))
        logger.info("created product: %s", spec["code"])


async def main() -> None:
    setup_logging()
    async with AsyncSessionLocal() as session:
        async with session.begin():
            roles = await _ensure_roles(session)
            await _ensure_users(session, roles)
            await _ensure_hospitals(session)
            await _ensure_products(session)
    logger.info("seed completed.")


if __name__ == "__main__":
    asyncio.run(main())
