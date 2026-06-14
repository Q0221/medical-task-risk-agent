"""v1 路由聚合。"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    agent,
    agent_traces,
    auth,
    health,
    knowledge,
    notifications,
    records,
    reports,
    risk,
    summary,
    tasks,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(admin.router)
api_router.include_router(auth.router)
api_router.include_router(tasks.router)
api_router.include_router(agent.router)
api_router.include_router(agent_traces.router)
api_router.include_router(knowledge.router)
api_router.include_router(notifications.router)
api_router.include_router(records.router)
api_router.include_router(reports.router)
api_router.include_router(risk.router)
api_router.include_router(summary.router)
