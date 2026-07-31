from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.integrations.max.client import MaxApiClient


def main() -> None:
    client = MaxApiClient.from_settings()
    deleted = client.unsubscribe_all_webhooks()
    print(f"deleted={len(deleted)}")
    for url in deleted:
        print(url)


if __name__ == "__main__":
    main()
