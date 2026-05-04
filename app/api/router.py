from __future__ import annotations

from fastapi import APIRouter

from app.api.routes.health import router as health_router
from app.api.routes.max_webhook import router as max_webhook_router


api_router = APIRouter()
api_router.include_router(health_router, prefix="/api")
api_router.include_router(max_webhook_router, prefix="/api")
