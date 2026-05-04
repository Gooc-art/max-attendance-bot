from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from app.config import get_settings
from app.bot.router import MaxWebhookRouter
from app.schemas.max import MaxUpdate, MaxWebhookResponse


router = APIRouter(tags=["max"])
webhook_router = MaxWebhookRouter()


@router.post("/webhooks/max", response_model=MaxWebhookResponse)
def receive_max_webhook(
    payload: MaxUpdate,
    x_max_bot_api_secret: str = Header(default="", alias="X-Max-Bot-Api-Secret"),
) -> MaxWebhookResponse:
    settings = get_settings()
    if settings.max_bot_secret and x_max_bot_api_secret != settings.max_bot_secret:
        raise HTTPException(status_code=403, detail="Invalid MAX secret header")
    return webhook_router.handle_event(payload)
