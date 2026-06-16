from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.office_sealing import OfficeSealingService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["female", "male", "initial", "final"])
    args = parser.parse_args()

    service = OfficeSealingService()
    if args.kind in {"female", "initial"}:
        sent = service.send_reminders_for_gender("female")
    else:
        sent = service.send_reminders_for_gender("male")
    print(f"office seal {args.kind} reminders sent: {sent}")


if __name__ == "__main__":
    main()
