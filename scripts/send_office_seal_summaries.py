from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.repositories.runtime_marker_repository import RuntimeMarkerRepository
from app.services.office_sealing import OfficeSealingService


def main() -> None:
    settings = get_settings()
    today = datetime.now(ZoneInfo(settings.office_seal_company_timezone)).date().isoformat()
    marker_key = f"scheduler:office_seal_summaries:{today}"
    markers = RuntimeMarkerRepository()
    if not markers.claim(marker_key, "scheduler", lease_seconds=900):
        print("office seal summaries skipped: another leader is running")
        return
    try:
        sent = OfficeSealingService().send_auto_summaries()
    except Exception:
        markers.release(marker_key)
        raise
    markers.complete(marker_key, ttl_seconds=60 * 60 * 24)
    print(f"office seal summaries sent: {sent}")


if __name__ == "__main__":
    main()
