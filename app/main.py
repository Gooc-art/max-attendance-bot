from __future__ import annotations

from typing import Dict

from fastapi import FastAPI

from app.api.router import api_router
from app.config import get_settings
from app.db.base import init_db
from app.services.demo_data import ensure_demo_approvals


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.app_debug,
)
app.include_router(api_router)


@app.on_event("startup")
def startup() -> None:
    init_db()
    ensure_demo_approvals()


@app.get("/", tags=["root"])
def root() -> Dict[str, str]:
    return {
        "service": settings.app_name,
        "status": "ok",
        "docs": "/docs",
    }
