from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.integrations.max.client import MaxApiClient
from app.services.max_webhook_url import resolve_webhook_url

from scripts.set_env_value import set_env_value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Register MAX webhook on the current public URL")
    parser.add_argument("--url", default="", help="Explicit public URL or webhook URL override")
    parser.add_argument(
        "--tunnel-url-file",
        default=str(ROOT / "run" / "localhostrun.url"),
        help="Path to the file with the current localhost.run public URL",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    settings = get_settings()
    client = MaxApiClient.from_settings()
    webhook_url = resolve_webhook_url(
        explicit_url=args.url,
        env_url=settings.max_bot_webhook_url,
        tunnel_url_file=Path(args.tunnel_url_file),
    )

    if not webhook_url:
        raise SystemExit("MAX_BOT_WEBHOOK_URL is empty and tunnel URL file is missing")
    if not settings.max_bot_secret:
        raise SystemExit("MAX_BOT_SECRET is empty")
    if not client.is_configured():
        raise SystemExit("MAX_BOT_TOKEN is empty")

    if webhook_url != settings.max_bot_webhook_url:
        env_path = ROOT / ".env"
        set_env_value(env_path, "MAX_BOT_WEBHOOK_URL", webhook_url)

    print("Registering webhook:", webhook_url)

    subscriptions = client.get_subscriptions().get("subscriptions", [])
    for subscription in subscriptions:
        url = subscription.get("url")
        if url and url != webhook_url:
            print("Removing stale subscription:", url)
            print(client.unsubscribe_webhook(url))

    result = client.register_webhook(
        url=webhook_url,
        update_types=["message_created", "message_callback", "bot_started"],
        secret=settings.max_bot_secret,
    )
    print(result)


if __name__ == "__main__":
    main()
