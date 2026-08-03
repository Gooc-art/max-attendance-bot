from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic
from typing import Any

from pydantic import ValidationError

from app.bot.router import MaxWebhookRouter
from app.config import get_settings
from app.db.base import init_db
from app.integrations.max.client import MaxApiClient
from app.repositories.runtime_marker_repository import RuntimeMarkerRepository
from app.schemas.max import MaxUpdate


logger = logging.getLogger(__name__)
WEBHOOK_CLEANUP_INTERVAL_SECONDS = 60


def extract_updates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("updates", "results", "items", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def extract_response_marker(payload: dict[str, Any]) -> str:
    for key in ("marker", "next_marker", "offset"):
        value = payload.get(key)
        if value is not None:
            return str(value)
    return ""


def extract_update_marker(update: dict[str, Any]) -> str:
    for key in ("marker", "update_id", "id", "event_id", "offset"):
        value = update.get(key)
        if value is not None:
            return str(value)
    return ""


def extract_update_payload(update: dict[str, Any]) -> dict[str, Any]:
    for key in ("update", "payload", "event"):
        value = update.get(key)
        if isinstance(value, dict):
            return value
    return update


def load_marker(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def save_marker(path: Path, marker: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(marker, encoding="utf-8")


def handle_polled_update(router: MaxWebhookRouter, markers: RuntimeMarkerRepository, raw_update: dict[str, Any]) -> bool:
    try:
        update = MaxUpdate.model_validate(extract_update_payload(raw_update))
    except ValidationError:
        logger.warning("MAX polling skipped invalid update", exc_info=True)
        return True

    dedup_key = router.incoming_dedup_key(update)
    if dedup_key and not markers.claim(dedup_key, "incoming", lease_seconds=120):
        logger.info("MAX polling duplicate suppressed key=%s", dedup_key)
        return True
    try:
        router.handle_event(update)
    except Exception:
        if dedup_key:
            markers.release(dedup_key)
        logger.exception("MAX polling update failed")
        return False
    if dedup_key:
        markers.complete(dedup_key, ttl_seconds=600)
    return True


def handle_polled_updates(
    router: MaxWebhookRouter,
    markers: RuntimeMarkerRepository,
    updates: list[dict[str, Any]],
    concurrency: int = 1,
) -> tuple[bool, str]:
    if not updates:
        return True, ""

    workers = max(int(concurrency or 1), 1)
    if workers == 1 or len(updates) == 1:
        results = [handle_polled_update(router, markers, raw_update) for raw_update in updates]
    else:
        with ThreadPoolExecutor(max_workers=min(workers, len(updates))) as executor:
            results = list(executor.map(lambda raw_update: handle_polled_update(router, markers, raw_update), updates))

    all_succeeded = True
    last_marker = ""
    for raw_update, ok in zip(updates, results):
        if not ok:
            all_succeeded = False
            break
        update_marker = extract_update_marker(raw_update)
        if update_marker:
            last_marker = update_marker
    return all_succeeded, last_marker


def delete_stale_webhooks(client: MaxApiClient) -> None:
    try:
        deleted_webhooks = client.unsubscribe_all_webhooks()
        if deleted_webhooks:
            logger.info("MAX polling deleted stale webhooks count=%s", len(deleted_webhooks))
    except Exception:
        logger.warning("MAX polling could not delete stale webhooks", exc_info=True)


def run_polling() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=logging.DEBUG if settings.app_debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    init_db()

    client = MaxApiClient.from_settings()
    client.request_timeout_seconds = max(settings.polling_timeout_seconds + 1, 2)
    delete_stale_webhooks(client)
    next_webhook_cleanup_at = monotonic() + WEBHOOK_CLEANUP_INTERVAL_SECONDS
    router = MaxWebhookRouter(async_callback_outbound=True, async_user_activity=True)
    markers = RuntimeMarkerRepository()
    marker_path = Path(settings.polling_marker_file)
    marker = load_marker(marker_path)
    polling_concurrency = max(int(getattr(settings, "polling_concurrency", 1) or 1), 1)

    logger.info("MAX polling started marker=%s concurrency=%s", marker or "<empty>", polling_concurrency)
    while True:
        if monotonic() >= next_webhook_cleanup_at:
            delete_stale_webhooks(client)
            next_webhook_cleanup_at = monotonic() + WEBHOOK_CLEANUP_INTERVAL_SECONDS
        try:
            response = client.get_updates(
                marker=marker or None,
                timeout_seconds=settings.polling_timeout_seconds,
                limit=settings.polling_limit,
            )
        except KeyboardInterrupt:
            raise
        except TimeoutError:
            logger.warning("MAX polling get_updates timed out")
            time.sleep(settings.polling_idle_sleep_seconds)
            continue
        except Exception:
            logger.exception("MAX polling loop failed")
            time.sleep(settings.polling_error_sleep_seconds)
            continue

        try:
            updates = extract_updates(response)
            response_marker = extract_response_marker(response)
            if not updates and response_marker and response_marker != marker:
                marker = response_marker
                save_marker(marker_path, marker)

            all_succeeded, batch_marker = handle_polled_updates(
                router,
                markers,
                updates,
                concurrency=polling_concurrency,
            )
            if batch_marker and batch_marker != marker:
                marker = batch_marker
                save_marker(marker_path, marker)
            if all_succeeded and response_marker and response_marker != marker:
                marker = response_marker
                save_marker(marker_path, marker)

            if not updates:
                time.sleep(settings.polling_idle_sleep_seconds)
        except KeyboardInterrupt:
            raise
        except Exception:
            logger.exception("MAX polling loop failed")
            time.sleep(settings.polling_error_sleep_seconds)


if __name__ == "__main__":
    run_polling()
