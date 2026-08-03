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
    max_api_timeout_seconds: int
    max_delete_previous_message: bool
    polling_marker_file: str
    polling_timeout_seconds: int
    polling_limit: int
    polling_concurrency: int
    polling_idle_sleep_seconds: int
    polling_error_sleep_seconds: int
    google_service_account_file: str
    google_sheets_spreadsheet_id: str
    google_sheets_employee_range: str
    google_sheets_schedule_range: str
    google_sheets_cache_ttl_seconds: int
    office_seal_company_timezone: str
    office_seal_window_start: str
    office_seal_window_end: str
    office_seal_photo_dir: str
    public_base_url: str
    weather_latitude: str
    weather_longitude: str
    weather_cache_ttl_seconds: int
    weather_location_ttl_seconds: int


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
        max_api_timeout_seconds=int(os.getenv("MAX_API_TIMEOUT_SECONDS", "3")),
        max_delete_previous_message=_to_bool(os.getenv("MAX_DELETE_PREVIOUS_MESSAGE"), default=True),
        polling_marker_file=os.getenv("POLLING_MARKER_FILE", str(BASE_DIR / "run" / "max_polling.marker")),
        polling_timeout_seconds=int(os.getenv("POLLING_TIMEOUT_SECONDS", "1")),
        polling_limit=int(os.getenv("POLLING_LIMIT", "100")),
        polling_concurrency=int(os.getenv("POLLING_CONCURRENCY", "2")),
        polling_idle_sleep_seconds=int(os.getenv("POLLING_IDLE_SLEEP_SECONDS", "1")),
        polling_error_sleep_seconds=int(os.getenv("POLLING_ERROR_SLEEP_SECONDS", "5")),
        google_service_account_file=os.getenv(
            "GOOGLE_SERVICE_ACCOUNT_FILE",
            "/Users/goocbk.ru/secure/attendance-max-bot-service-account.json",
        ),
        google_sheets_spreadsheet_id=os.getenv(
            "GOOGLE_SHEETS_SPREADSHEET_ID",
            "1tg5umqy7-72LMLEaXu6n29OvGDSpkOE_adw_7PxsP54",
        ),
        google_sheets_employee_range=os.getenv("GOOGLE_SHEETS_EMPLOYEE_RANGE", "Сотрудники!A:R"),
        google_sheets_schedule_range=os.getenv("GOOGLE_SHEETS_SCHEDULE_RANGE", "Графики!A:X"),
        google_sheets_cache_ttl_seconds=int(os.getenv("GOOGLE_SHEETS_CACHE_TTL_SECONDS", "300")),
        office_seal_company_timezone=os.getenv("OFFICE_SEAL_COMPANY_TIMEZONE", "Europe/Amsterdam"),
        office_seal_window_start=os.getenv("OFFICE_SEAL_WINDOW_START", "18:00"),
        office_seal_window_end=os.getenv("OFFICE_SEAL_WINDOW_END", "22:00"),
        office_seal_photo_dir=os.getenv("OFFICE_SEAL_PHOTO_DIR", str(BASE_DIR / "data" / "office_seal_photos")),
        public_base_url=os.getenv("PUBLIC_BASE_URL", os.getenv("MAX_BOT_WEBHOOK_URL", "")).rstrip("/"),
        weather_latitude=os.getenv("WEATHER_LATITUDE", ""),
        weather_longitude=os.getenv("WEATHER_LONGITUDE", ""),
        weather_cache_ttl_seconds=int(os.getenv("WEATHER_CACHE_TTL_SECONDS", "3600")),
        weather_location_ttl_seconds=int(os.getenv("WEATHER_LOCATION_TTL_SECONDS", "2592000")),
    )
