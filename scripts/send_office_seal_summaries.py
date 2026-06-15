from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.office_sealing import OfficeSealingService


def main() -> None:
    sent = OfficeSealingService().send_auto_summaries()
    print(f"office seal summaries sent: {sent}")


if __name__ == "__main__":
    main()
