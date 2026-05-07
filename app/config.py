from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _to_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_host: str
    app_port: int
    app_debug: bool
    database_url: str
    max_api_base_url: str
    max_api_version: str
    max_bot_token: str
    max_bot_secret: str
    max_bot_webhook_url: str
    google_service_account_file: str
    google_sheets_spreadsheet_id: str
    google_sheets_employee_range: str
    google_sheets_schedule_range: str
    google_sheets_cache_ttl_seconds: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        app_name="MAX Attendance Bot",
        app_host=os.getenv("APP_HOST", "0.0.0.0"),
        app_port=int(os.getenv("APP_PORT", "8000")),
        app_debug=_to_bool(os.getenv("APP_DEBUG"), default=False),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./data/attendance_bot.db"),
        max_api_base_url=os.getenv("MAX_API_BASE_URL", "https://platform-api.max.ru/"),
        max_api_version=os.getenv("MAX_API_VERSION", "1.2.5"),
        max_bot_token=os.getenv("MAX_BOT_TOKEN", ""),
        max_bot_secret=os.getenv("MAX_BOT_SECRET", ""),
        max_bot_webhook_url=os.getenv("MAX_BOT_WEBHOOK_URL", ""),
        google_service_account_file=os.getenv(
            "GOOGLE_SERVICE_ACCOUNT_FILE",
            "/Users/goocbk.ru/secure/attendance-max-bot-service-account.json",
        ),
        google_sheets_spreadsheet_id=os.getenv(
            "GOOGLE_SHEETS_SPREADSHEET_ID",
            "1tg5umqy7-72LMLEaXu6n29OvGDSpkOE_adw_7PxsP54",
        ),
        google_sheets_employee_range=os.getenv("GOOGLE_SHEETS_EMPLOYEE_RANGE", "Сотрудники!A:Q"),
        google_sheets_schedule_range=os.getenv("GOOGLE_SHEETS_SCHEDULE_RANGE", "Графики!A:L"),
        google_sheets_cache_ttl_seconds=int(os.getenv("GOOGLE_SHEETS_CACHE_TTL_SECONDS", "300")),
    )
