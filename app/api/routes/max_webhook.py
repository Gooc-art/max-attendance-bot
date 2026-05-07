from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException

from app.config import get_settings
from app.bot.router import MaxWebhookRouter
from app.schemas.max import MaxUpdate, MaxWebhookResponse


router = APIRouter(tags=["max"])
webhook_router = MaxWebhookRouter()
logger = logging.getLogger(__name__)


@router.post("/webhooks/max", response_model=MaxWebhookResponse)
def receive_max_webhook(
    payload: MaxUpdate,
    x_max_bot_api_secret: str = Header(default="", alias="X-Max-Bot-Api-Secret"),
) -> MaxWebhookResponse:
    settings = get_settings()
    if settings.max_bot_secret and x_max_bot_api_secret != settings.max_bot_secret:
        raise HTTPException(status_code=403, detail="Invalid MAX secret header")
    logger.info(
        "MAX webhook received update_type=%s chat_id=%s user_id=%s has_message=%s has_callback=%s",
        payload.update_type,
        payload.chat_id,
        payload.user.user_id if payload.user else None,
        bool(payload.message),
        bool(payload.callback),
    )
    if payload.message and payload.message.body.attachments:
        logger.info(
            "MAX webhook attachments mid=%s attachment_types=%s filenames=%s",
            payload.message.body.mid,
            [attachment.type for attachment in payload.message.body.attachments],
            [attachment.filename for attachment in payload.message.body.attachments],
        )
    return webhook_router.handle_event(payload)
