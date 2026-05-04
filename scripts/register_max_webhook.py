from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.integrations.max.client import MaxApiClient


def main() -> None:
    settings = get_settings()
    client = MaxApiClient.from_settings()

    if not settings.max_bot_webhook_url:
        raise SystemExit("MAX_BOT_WEBHOOK_URL is empty")
    if not settings.max_bot_secret:
        raise SystemExit("MAX_BOT_SECRET is empty")
    if not client.is_configured():
        raise SystemExit("MAX_BOT_TOKEN is empty")

    result = client.register_webhook(
        url=settings.max_bot_webhook_url,
        update_types=["message_created", "message_callback", "bot_started"],
        secret=settings.max_bot_secret,
    )
    print(result)


if __name__ == "__main__":
    main()
