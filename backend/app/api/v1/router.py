"""v1 路由聚合。"""

from fastapi import APIRouter

from app.api.v1.endpoints import agent, health, tasks

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(tasks.router)
api_router.include_router(agent.router)
