from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.repositories.runtime_marker_repository import RuntimeMarkerRepository
from app.services.office_sealing import OfficeSealingService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["female", "male", "initial", "final"])
    args = parser.parse_args()

    settings = get_settings()
    today = datetime.now(ZoneInfo(settings.office_seal_company_timezone)).date().isoformat()
    marker_key = f"scheduler:office_seal_reminders:{today}:{args.kind}"
    markers = RuntimeMarkerRepository()
    if not markers.claim(marker_key, "scheduler", lease_seconds=900):
        print(f"office seal {args.kind} reminders skipped: another leader is running")
        return

    service = OfficeSealingService()
    try:
        if args.kind in {"female", "initial"}:
            sent = service.send_reminders_for_gender("female")
        else:
            sent = service.send_reminders_for_gender("male")
    except Exception:
        markers.release(marker_key)
        raise
    markers.complete(marker_key, ttl_seconds=60 * 60 * 24)
    print(f"office seal {args.kind} reminders sent: {sent}")


if __name__ == "__main__":
    main()
