from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.office_sealing import OfficeSealingService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["initial", "final"])
    args = parser.parse_args()

    service = OfficeSealingService()
    if args.kind == "initial":
        sent = service.send_initial_reminders()
    else:
        sent = service.send_final_reminders()
    print(f"office seal {args.kind} reminders sent: {sent}")


if __name__ == "__main__":
    main()
