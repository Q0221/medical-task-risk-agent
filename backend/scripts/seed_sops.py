"""将 rag/sop_data.py 中的内置 SOP 文档灌入 sop_documents 表。

运行方式（在 backend/ 目录下）：
    python -m scripts.seed_sops
    python -m scripts.seed_sops --reset   # 先清空再重灌
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select


async def _seed(reset: bool = False) -> None:
    from app.core.db import AsyncSessionLocal
    from app.models.sop_document import SopDocument
    from app.rag.sop_data import BUILTIN_SOPS

    # 分类映射（根据 SOP 编号推断）
    _CATEGORY_MAP = {
        "SOP-ADV": "不良事件",
        "SOP-DEV": "设备异常",
        "SOP-CMP": "合规审核",
        "SOP-FLW": "客户跟进",
        "SOP-QA": "质量控制",
    }
    _DEPT_MAP = {
        "SOP-ADV": "医学支持部",
        "SOP-DEV": "技术服务部",
        "SOP-CMP": "合规部",
        "SOP-FLW": "客户服务部",
        "SOP-QA": "质量管理部",
    }

    async with AsyncSessionLocal() as session:
        if reset:
            existing = (
                await session.execute(
                    select(SopDocument).where(SopDocument.deleted_at.is_(None))
                )
            ).scalars().all()
            for doc in existing:
                from datetime import datetime, timezone
                doc.deleted_at = datetime.now(timezone.utc)
            await session.commit()
            print(f"[seed_sops] 已清空 {len(existing)} 条 SOP 记录")

        inserted = 0
        for sop in BUILTIN_SOPS:
            # 幂等：code 已存在的 active 版本跳过
            exists = (
                await session.execute(
                    select(SopDocument).where(
                        SopDocument.code == sop.doc_id,
                        SopDocument.status == "active",
                        SopDocument.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if exists:
                print(f"[seed_sops] skip existing: {sop.doc_id}")
                continue

            prefix = "-".join(sop.doc_id.split("-")[:2])
            doc = SopDocument(
                code=sop.doc_id,
                title=sop.title,
                category=_CATEGORY_MAP.get(prefix, "通用"),
                department=_DEPT_MAP.get(prefix, "综合部门"),
                version="v1.0",
                tags=sop.keywords[:6],
                content=sop.content,
                status="active",
                hit_count=0,
            )
            session.add(doc)
            inserted += 1

        await session.commit()
        print(f"[seed_sops] 完成，新增 {inserted} 条 SOP 文档")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed SOP documents into DB")
    parser.add_argument("--reset", action="store_true", help="先清空再重灌")
    args = parser.parse_args()
    asyncio.run(_seed(reset=args.reset))


if __name__ == "__main__":
    main()
