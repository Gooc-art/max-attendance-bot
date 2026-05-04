from __future__ import annotations

from typing import Dict, Union

from fastapi import APIRouter

from app.config import get_settings


router = APIRouter(tags=["health"])


@router.get("/health")
def healthcheck() -> Dict[str, Union[str, bool]]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "max_token_configured": bool(settings.max_bot_token),
    }
