from fastapi import APIRouter

from src.api.webhook import router as webhook_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(webhook_router, prefix="/webhook")
