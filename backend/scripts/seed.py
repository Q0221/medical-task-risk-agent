"""灌入最小开发种子：7 角色 + 7 员工 + 3 医院 + 3 产品。

运行方式（在 backend/ 目录下）：

    python -m scripts.seed

每张表灌满 50 条标准虚拟数据（推荐，一次执行长期可用）：

    python -m scripts.seed_bulk
    python -m scripts.seed_bulk --reset   # 清空 DEMO_ 数据后重灌

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
from app.models.hospital import Hospital  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.models.user import Role, User, UserRole  # noqa: E402
from scripts.seed_data import HOSPITALS, PRODUCTS, ROLES, USERS  # noqa: E402

logger = get_logger("seed")


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
