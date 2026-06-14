"""业务档案接口。

已实现：
- GET /records/stats               总览统计（医院数、产品数、风险任务数等）
- GET /records/hospitals           医院列表（搜索、筛选、分页、含任务统计）
- GET /records/hospitals/options   医院筛选枚举值（level、region）
- GET /records/hospitals/{id}      医院详情（含近期任务 + 关联产品）
- GET /records/products            产品列表（搜索、筛选、分页、含任务统计）
- GET /records/products/options    产品筛选枚举值（category、business_unit）
- GET /records/products/{id}       产品详情（含近期任务 + 关联医院）
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_current_user
from app.core.exceptions import BizException
from app.core.response import success
from app.schemas.records import (
    HospitalDetail,
    HospitalListItem,
    HospitalListResponse,
    ProductDetail,
    ProductListItem,
    ProductListResponse,
    RecordStats,
)
from app.services import records_service
from app.services.auth_service import CurrentUser

router = APIRouter(prefix="/records", tags=["records"])


@router.get("/stats", summary="档案总览统计")
async def get_stats(
    _: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    """返回档案页顶部的四个汇总数字。"""
    data = await records_service.get_record_stats(session)
    return success(RecordStats(**data).model_dump())


# ---------------------------------------------------------------------------
# 医院档案
# ---------------------------------------------------------------------------

@router.get("/hospitals/options", summary="医院筛选枚举值")
async def get_hospital_options(
    _: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    """返回可用的医院等级（level）和地区（region）枚举值列表，供前端下拉框使用。"""
    data = await records_service.get_hospital_filter_options(session)
    return success(data)


@router.get("/hospitals/{hospital_id}", summary="医院详情")
async def get_hospital_detail(
    hospital_id: int = Path(..., ge=1),
    _: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    """返回指定医院的完整档案，包含近 10 条关联任务和关联产品名称列表。"""
    data = await records_service.get_hospital_detail(session, hospital_id)
    if data is None:
        raise BizException(code=4044, message=f"医院 id={hospital_id} 不存在")
    return success(HospitalDetail(**data).model_dump(mode="json"))


@router.get("/hospitals", summary="医院列表")
async def list_hospitals(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(default=None, description="按医院名称或地区搜索"),
    level: Optional[str] = Query(default=None, description="医院等级筛选"),
    region: Optional[str] = Query(default=None, description="地区筛选"),
    _: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    """分页获取医院列表，每条记录附带累计任务数、进行中任务数、高风险任务数。"""
    items, total = await records_service.list_hospitals(
        session,
        page=page,
        page_size=page_size,
        search=search,
        level=level,
        region=region,
    )
    resp = HospitalListResponse(
        items=[HospitalListItem(**item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )
    return success(resp.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# 产品档案
# ---------------------------------------------------------------------------

@router.get("/products/options", summary="产品筛选枚举值")
async def get_product_options(
    _: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    """返回可用的产品类别（category）和事业部（business_unit）枚举值列表。"""
    data = await records_service.get_product_filter_options(session)
    return success(data)


@router.get("/products/{product_id}", summary="产品详情")
async def get_product_detail(
    product_id: int = Path(..., ge=1),
    _: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    """返回指定产品的完整档案，包含近 10 条关联任务和关联医院名称列表。"""
    data = await records_service.get_product_detail(session, product_id)
    if data is None:
        raise BizException(code=4044, message=f"产品 id={product_id} 不存在")
    return success(ProductDetail(**data).model_dump(mode="json"))


@router.get("/products", summary="产品列表")
async def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(default=None, description="按产品名称或类别搜索"),
    category: Optional[str] = Query(default=None, description="产品类别筛选"),
    business_unit: Optional[str] = Query(default=None, description="事业部筛选"),
    _: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    """分页获取产品列表，每条记录附带累计任务数、进行中任务数、高风险任务数。"""
    items, total = await records_service.list_products(
        session,
        page=page,
        page_size=page_size,
        search=search,
        category=category,
        business_unit=business_unit,
    )
    resp = ProductListResponse(
        items=[ProductListItem(**item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )
    return success(resp.model_dump(mode="json"))
