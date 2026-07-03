from __future__ import annotations

import logging
from time import perf_counter

from fastapi import APIRouter, Header, HTTPException

from app.config import get_settings
from app.bot.router import MaxWebhookRouter
from app.repositories.runtime_marker_repository import RuntimeMarkerRepository
from app.schemas.max import MaxOutboundMessage, MaxUpdate, MaxWebhookResponse


router = APIRouter(tags=["max"])
webhook_router = MaxWebhookRouter(async_callback_outbound=True)
runtime_markers = RuntimeMarkerRepository()
logger = logging.getLogger(__name__)


@router.post("/webhooks/max", response_model=MaxWebhookResponse)
def receive_max_webhook(
    payload: MaxUpdate,
    x_max_bot_api_secret: str = Header(default="", alias="X-Max-Bot-Api-Secret"),
) -> MaxWebhookResponse:
    started_at = perf_counter()
    settings = get_settings()
    if settings.max_bot_secret and x_max_bot_api_secret and x_max_bot_api_secret != settings.max_bot_secret:
        raise HTTPException(status_code=403, detail="Invalid MAX secret header")
    if settings.max_bot_secret and not x_max_bot_api_secret:
        logger.warning("MAX webhook secret header is missing; accepting request for compatibility")
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
    dedup_key = webhook_router.incoming_dedup_key(payload)
    if dedup_key and not runtime_markers.claim(dedup_key, "incoming", lease_seconds=120):
        logger.info("MAX webhook duplicate suppressed key=%s", dedup_key)
        return MaxWebhookResponse(ok=True, role="", menu=[], outbound=MaxOutboundMessage(text="", buttons=[]))

    try:
        response = webhook_router.handle_event(payload)
    except Exception:
        if dedup_key:
            runtime_markers.release(dedup_key)
        raise
    if dedup_key:
        runtime_markers.complete(dedup_key, ttl_seconds=600)
    elapsed_ms = round((perf_counter() - started_at) * 1000, 1)
    logger.info(
        "MAX webhook handled update_type=%s chat_id=%s user_id=%s role=%s active_flow=%s elapsed_ms=%s",
        payload.update_type,
        payload.chat_id,
        payload.user.user_id if payload.user else None,
        response.role,
        response.active_flow,
        elapsed_ms,
    )
    return response
