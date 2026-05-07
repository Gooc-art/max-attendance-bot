from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

from app.config import get_settings


GOOGLE_SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]


@dataclass(frozen=True)
class GoogleSheetsScheduleRecord:
    schedule_id: str = ""
    schedule_name: str = ""
    monday_start: str = ""
    tuesday_start: str = ""
    wednesday_start: str = ""
    thursday_start: str = ""
    friday_start: str = ""
    saturday_start: str = ""
    sunday_start: str = ""
    late_after_minutes: int = 10
    is_active: bool = True
    comment: str = ""

    def planned_start_for(self, event_date: date) -> str:
        weekday = event_date.weekday()
        mapping = {
            0: self.monday_start,
            1: self.tuesday_start,
            2: self.wednesday_start,
            3: self.thursday_start,
            4: self.friday_start,
            5: self.saturday_start,
            6: self.sunday_start,
        }
        return mapping.get(weekday, "")


class GoogleSheetsScheduleService:
    def __init__(
        self,
        spreadsheet_id: str | None = None,
        service_account_file: str | None = None,
        schedule_range: str | None = None,
        cache_ttl_seconds: int = 300,
    ) -> None:
        settings = get_settings()
        self.spreadsheet_id = spreadsheet_id or settings.google_sheets_spreadsheet_id
        self.service_account_file = service_account_file or settings.google_service_account_file
        self.schedule_range = schedule_range or settings.google_sheets_schedule_range
        self.cache_ttl_seconds = cache_ttl_seconds or settings.google_sheets_cache_ttl_seconds
        self._cached_records: List[GoogleSheetsScheduleRecord] = []
        self._cached_at: datetime | None = None

    @classmethod
    def from_settings(cls) -> "GoogleSheetsScheduleService":
        settings = get_settings()
        return cls(
            spreadsheet_id=settings.google_sheets_spreadsheet_id,
            service_account_file=settings.google_service_account_file,
            schedule_range=settings.google_sheets_schedule_range,
            cache_ttl_seconds=settings.google_sheets_cache_ttl_seconds,
        )

    def is_configured(self) -> bool:
        return bool(self.spreadsheet_id and self.service_account_file and Path(self.service_account_file).exists())

    def list_schedules(self, refresh: bool = False) -> List[GoogleSheetsScheduleRecord]:
        if not self.is_configured():
            return []
        if not refresh and self._cache_is_fresh():
            return list(self._cached_records)
        values = self._fetch_values()
        records = self._parse_values(values)
        self._cached_records = records
        self._cached_at = datetime.utcnow()
        return list(records)

    def get_by_schedule_id(self, schedule_id: str, refresh: bool = False) -> Optional[GoogleSheetsScheduleRecord]:
        if not schedule_id:
            return None
        for record in self.list_schedules(refresh=refresh):
            if record.schedule_id == schedule_id:
                return record
        return None

    def get_by_schedule_name(self, schedule_name: str, refresh: bool = False) -> Optional[GoogleSheetsScheduleRecord]:
        if not schedule_name:
            return None
        for record in self.list_schedules(refresh=refresh):
            if record.schedule_name == schedule_name:
                return record
        return None

    def resolve_planned_start(
        self,
        *,
        schedule_id: str = "",
        schedule_name: str = "",
        event_date: date,
        fallback: str = "08:30",
    ) -> str:
        record = self.get_by_schedule_id(schedule_id, refresh=True) if schedule_id else None
        if record is None and schedule_name:
            record = self.get_by_schedule_name(schedule_name, refresh=True)
        if record is None:
            return fallback
        planned = record.planned_start_for(event_date)
        return planned or ""

    def resolve_late_after_minutes(
        self,
        *,
        schedule_id: str = "",
        schedule_name: str = "",
        fallback: int = 10,
    ) -> int:
        record = self.get_by_schedule_id(schedule_id, refresh=True) if schedule_id else None
        if record is None and schedule_name:
            record = self.get_by_schedule_name(schedule_name, refresh=True)
        if record is None:
            return fallback
        return record.late_after_minutes

    def _cache_is_fresh(self) -> bool:
        if self._cached_at is None:
            return False
        return (datetime.utcnow() - self._cached_at).total_seconds() <= self.cache_ttl_seconds

    def _fetch_values(self) -> List[List[str]]:
        credentials = self._load_credentials()
        sheets_service = self._build_sheets_service(credentials)
        response = (
            sheets_service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.spreadsheet_id,
                range=self.schedule_range,
            )
            .execute()
        )
        return response.get("values", [])

    def _load_credentials(self):
        from google.oauth2 import service_account

        return service_account.Credentials.from_service_account_file(
            self.service_account_file,
            scopes=GOOGLE_SHEETS_SCOPES,
        )

    def _build_sheets_service(self, credentials):
        from googleapiclient.discovery import build

        return build("sheets", "v4", credentials=credentials, cache_discovery=False)

    def _parse_values(self, values: List[List[str]]) -> List[GoogleSheetsScheduleRecord]:
        if not values:
            return []

        headers = [self._normalize_cell(cell) for cell in values[0]]
        records: List[GoogleSheetsScheduleRecord] = []
        for row in values[1:]:
            if not any(self._normalize_cell(cell) for cell in row):
                continue
            data = {
                headers[index]: self._normalize_cell(cell)
                for index, cell in enumerate(row)
                if index < len(headers) and headers[index]
            }
            schedule_name = self._pick(data, "Наименование_графика", "schedule_name")
            schedule_id = self._pick(data, "ID_графика", "schedule_id")
            if not schedule_id and not schedule_name:
                continue
            records.append(
                GoogleSheetsScheduleRecord(
                    schedule_id=schedule_id,
                    schedule_name=schedule_name,
                    monday_start=self._pick(data, "Понедельник_начало", "monday_start"),
                    tuesday_start=self._pick(data, "Вторник_начало", "tuesday_start"),
                    wednesday_start=self._pick(data, "Среда_начало", "wednesday_start"),
                    thursday_start=self._pick(data, "Четверг_начало", "thursday_start"),
                    friday_start=self._pick(data, "Пятница_начало", "friday_start"),
                    saturday_start=self._pick(data, "Суббота_начало", "saturday_start"),
                    sunday_start=self._pick(data, "Воскресенье_начало", "sunday_start"),
                    late_after_minutes=self._to_int(self._pick(data, "Допустимое_опоздание_мин", "late_after_minutes"), default=10),
                    is_active=self._to_bool(self._pick(data, "Активен", "is_active"), default=True),
                    comment=self._pick(data, "Комментарий", "comment"),
                )
            )
        return records

    @staticmethod
    def _normalize_cell(value: object) -> str:
        return str(value).strip() if value is not None else ""

    @staticmethod
    def _pick(data: dict, *keys: str) -> str:
        for key in keys:
            value = data.get(key, "")
            if value:
                return value
        return ""

    @staticmethod
    def _to_bool(value: str, default: bool = False) -> bool:
        if not value:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on", "да"}

    @staticmethod
    def _to_int(value: str, default: int = 0) -> int:
        if not value:
            return default
        try:
            return int(float(value.replace(",", ".")))
        except ValueError:
            return default
