#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.base import init_db
from app.services.employee_directory_sync import EmployeeDirectorySyncService


def main() -> None:
    init_db()
    result = EmployeeDirectorySyncService().sync(refresh=True)
    if not result.configured:
        print("employee directory sync skipped: Google Sheets is not configured")
        return
    print(
        "employee directory synced: fetched={fetched} upserted={upserted}".format(
            fetched=result.fetched_rows,
            upserted=result.upserted_rows,
        )
    )


if __name__ == "__main__":
    main()
