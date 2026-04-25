"""Aggregator router: includes webhook, health, tasks sub-routers.

Roadmap requirement: src/api/router.py — aggregator for all API sub-routers.
"""

from fastapi import APIRouter

from src.api.health import router as health_router
from src.api.tasks import router as tasks_router
from src.api.webhook import router as webhook_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(webhook_router, prefix="/webhook")
api_router.include_router(health_router, prefix="/health")
api_router.include_router(tasks_router, prefix="/tasks")
