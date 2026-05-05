from __future__ import annotations

from fastapi import APIRouter

from app.api.routes.health import router as health_router
from app.api.routes.employee_directory import router as employee_directory_router
from app.api.routes.reports import router as reports_router
from app.api.routes.max_webhook import router as max_webhook_router
from app.api.routes.skud_imports import router as skud_imports_router


api_router = APIRouter()
api_router.include_router(health_router, prefix="/api")
api_router.include_router(employee_directory_router, prefix="/api")
api_router.include_router(reports_router, prefix="/api")
api_router.include_router(max_webhook_router, prefix="/api")
api_router.include_router(skud_imports_router, prefix="/api")
