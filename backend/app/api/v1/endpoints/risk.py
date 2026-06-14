"""风险中心接口。

已实现：
- GET    /risk/stats                   风险统计（指标卡）
- GET    /risk/records                 风险记录列表
- GET    /risk/records/task/{task_id}  某任务的全部风险记录
- GET    /risk/records/{record_id}     单条风险记录详情
- GET    /risk/tickets                 风险工单列表（escalated 任务）
- GET    /risk/rules                   风险规则列表
- POST   /risk/rules                   创建风险规则
- PATCH  /risk/rules/{rule_id}         更新风险规则
- DELETE /risk/rules/{rule_id}         删除风险规则
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_current_user, require_app_roles
from app.core.exceptions import BizException
from app.core.response import success
from app.schemas.risk import (
    RiskRecordListResponse,
    RiskRecordOut,
    RiskRuleCreateRequest,
    RiskRuleListResponse,
    RiskRuleOut,
    RiskRuleUpdateRequest,
    RiskStats,
    RiskTicketItem,
    RiskTicketListResponse,
)
from app.services import risk_record_service
from app.services.auth_service import CurrentUser, is_manager_or_admin

router = APIRouter(prefix="/risk", tags=["risk"])


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------

@router.get("/stats", summary="风险统计指标")
async def get_risk_stats(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    stats = await risk_record_service.get_risk_stats(session)
    return success(RiskStats(**stats).model_dump(mode="json"))


# ---------------------------------------------------------------------------
# 风险记录（注意静态路径 /records/task/{} 先于 /records/{} 注册）
# ---------------------------------------------------------------------------

@router.get("/records/task/{task_id}", summary="某任务的全部风险记录")
async def list_records_by_task(
    task_id: int = Path(..., ge=1),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    items = await risk_record_service.list_records_by_task(session, task_id)
    return success({
        "items": [RiskRecordOut.model_validate(r).model_dump(mode="json") for r in items],
        "total": len(items),
    })


@router.get("/records/{record_id}", summary="单条风险记录详情")
async def get_risk_record(
    record_id: int = Path(..., ge=1),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    record = await risk_record_service.get_risk_record(session, record_id)
    if record is None:
        raise BizException(code=4044, message=f"风险记录 id={record_id} 不存在")
    return success(RiskRecordOut.model_validate(record).model_dump(mode="json"))


@router.get("/records", summary="风险记录列表")
async def list_risk_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    task_id: Optional[int] = Query(default=None, ge=1),
    risk_level: Optional[str] = Query(default=None),
    review_status: Optional[str] = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    items, total = await risk_record_service.list_risk_records(
        session,
        page=page,
        page_size=page_size,
        task_id=task_id,
        risk_level=risk_level,
        review_status=review_status,
    )
    resp = RiskRecordListResponse(
        items=[RiskRecordOut.model_validate(r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
    )
    return success(resp.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# 风险工单
# ---------------------------------------------------------------------------

@router.get("/tickets", summary="风险工单列表（escalated 任务）")
async def list_risk_tickets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    risk_level: Optional[str] = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    items, total = await risk_record_service.list_risk_tickets(
        session,
        page=page,
        page_size=page_size,
        risk_level=risk_level,
    )
    resp = RiskTicketListResponse(
        items=[RiskTicketItem.model_validate(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
    )
    return success(resp.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# 风险规则（manager/admin 写，所有人读）
# ---------------------------------------------------------------------------

@router.get("/rules", summary="风险规则列表")
async def list_risk_rules(
    include_inactive: bool = Query(default=True),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict:
    items, total = await risk_record_service.list_risk_rules(
        session, include_inactive=include_inactive
    )
    resp = RiskRuleListResponse(
        items=[RiskRuleOut.model_validate(r) for r in items],
        total=total,
    )
    return success(resp.model_dump(mode="json"))


@router.post("/rules", summary="创建风险规则")
async def create_risk_rule(
    body: RiskRuleCreateRequest,
    current_user: CurrentUser = Depends(require_app_roles("manager", "admin")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    async with session.begin():
        rule = await risk_record_service.create_risk_rule(session, body)
    return success(RiskRuleOut.model_validate(rule).model_dump(mode="json"))


@router.patch("/rules/{rule_id}", summary="更新风险规则")
async def update_risk_rule(
    rule_id: int = Path(..., ge=1),
    body: RiskRuleUpdateRequest = ...,
    current_user: CurrentUser = Depends(require_app_roles("manager", "admin")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    async with session.begin():
        rule = await risk_record_service.update_risk_rule(session, rule_id, body)
    return success(RiskRuleOut.model_validate(rule).model_dump(mode="json"))


@router.delete("/rules/{rule_id}", summary="删除风险规则（软删除）")
async def delete_risk_rule(
    rule_id: int = Path(..., ge=1),
    current_user: CurrentUser = Depends(require_app_roles("manager", "admin")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    async with session.begin():
        await risk_record_service.delete_risk_rule(session, rule_id)
    return success({"rule_id": rule_id, "message": "规则已删除"})
