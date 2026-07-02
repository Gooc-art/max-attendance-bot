from __future__ import annotations

import logging
from typing import Dict

from fastapi import FastAPI

from app.api.router import api_router
from app.config import get_settings
from app.db.base import init_db


settings = get_settings()

logging.basicConfig(
    level=logging.DEBUG if settings.app_debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("app").setLevel(logging.DEBUG if settings.app_debug else logging.INFO)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.app_debug,
)
app.include_router(api_router)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/", tags=["root"])
def root() -> Dict[str, str]:
    return {
        "service": settings.app_name,
        "status": "ok",
        "docs": "/docs",
    }
