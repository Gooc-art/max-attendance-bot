from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
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
    monday_end: str = ""
    tuesday_start: str = ""
    tuesday_end: str = ""
    wednesday_start: str = ""
    wednesday_end: str = ""
    thursday_start: str = ""
    thursday_end: str = ""
    friday_start: str = ""
    friday_end: str = ""
    saturday_start: str = ""
    saturday_end: str = ""
    sunday_start: str = ""
    sunday_end: str = ""
    late_after_minutes: int = 10
    lunch_start: str = ""
    lunch_end: str = ""
    lunch_minutes: int = 0
    planned_minutes_per_day: int = 0
    lunch_mode: str = ""
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

    def planned_end_for(self, event_date: date) -> str:
        weekday = event_date.weekday()
        mapping = {
            0: self.monday_end,
            1: self.tuesday_end,
            2: self.wednesday_end,
            3: self.thursday_end,
            4: self.friday_end,
            5: self.saturday_end,
            6: self.sunday_end,
        }
        return mapping.get(weekday, "")

    def resolved_planned_minutes(self, event_date: date) -> int:
        if self.planned_minutes_per_day > 0:
            return self.planned_minutes_per_day
        start = self.planned_start_for(event_date)
        end = self.planned_end_for(event_date)
        if not start or not end:
            return 0
        try:
            start_dt = datetime.strptime(start, "%H:%M")
            end_dt = datetime.strptime(end, "%H:%M")
        except ValueError:
            return 0
        total = int((end_dt - start_dt).total_seconds() // 60)
        if total <= 0:
            return 0
        lunch_minutes = self.resolved_lunch_minutes()
        if lunch_minutes > 0:
            total = max(total - lunch_minutes, 0)
        return total

    def resolved_lunch_minutes(self) -> int:
        if self.lunch_minutes > 0:
            return self.lunch_minutes
        if self.lunch_start and self.lunch_end:
            try:
                start_dt = datetime.strptime(self.lunch_start, "%H:%M")
                end_dt = datetime.strptime(self.lunch_end, "%H:%M")
            except ValueError:
                return 0
            return max(int((end_dt - start_dt).total_seconds() // 60), 0)
        parsed = GoogleSheetsScheduleService._parse_lunch_window_from_text(self.comment)
        if parsed is None:
            parsed = GoogleSheetsScheduleService._parse_lunch_window_from_schedule_name(self.schedule_name)
        if parsed is None:
            return 0
        return parsed[2]

    def resolved_lunch_window(self) -> tuple[str, str]:
        if self.lunch_start and self.lunch_end:
            return self.lunch_start, self.lunch_end
        parsed = GoogleSheetsScheduleService._parse_lunch_window_from_text(self.comment)
        if parsed is None:
            parsed = GoogleSheetsScheduleService._parse_lunch_window_from_schedule_name(self.schedule_name)
        if parsed is None:
            return "", ""
        return parsed[0], parsed[1]


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
        self._cached_by_schedule_id: dict[str, GoogleSheetsScheduleRecord] = {}
        self._cached_by_schedule_name: dict[str, GoogleSheetsScheduleRecord] = {}
        self.logger = logging.getLogger(__name__)

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
        started_at = perf_counter()
        try:
            values = self._fetch_values()
            records = self._parse_values(values)
            self._cached_records = records
            self._rebuild_indexes(records)
            self._cached_at = datetime.now(timezone.utc)
            self.logger.info(
                "Google Sheets schedules loaded records=%s refresh=%s elapsed_ms=%.1f",
                len(records),
                refresh,
                (perf_counter() - started_at) * 1000,
            )
            return list(records)
        except Exception as exc:
            if self._cached_records:
                self.logger.warning(
                    "Google Sheets schedule fetch failed, using cached records=%s refresh=%s elapsed_ms=%.1f error=%s",
                    len(self._cached_records),
                    refresh,
                    (perf_counter() - started_at) * 1000,
                    exc,
                )
                return list(self._cached_records)
            self.logger.warning(
                "Google Sheets schedule fetch failed and cache is empty refresh=%s elapsed_ms=%.1f error=%s",
                refresh,
                (perf_counter() - started_at) * 1000,
                exc,
            )
            return []

    def get_by_schedule_id(self, schedule_id: str, refresh: bool = False) -> Optional[GoogleSheetsScheduleRecord]:
        if not schedule_id:
            return None
        if not refresh and self._cache_is_fresh() and self._cached_by_schedule_id:
            return self._cached_by_schedule_id.get(schedule_id)
        for record in self.list_schedules(refresh=refresh):
            if record.schedule_id == schedule_id:
                return record
        return None

    def get_by_schedule_name(self, schedule_name: str, refresh: bool = False) -> Optional[GoogleSheetsScheduleRecord]:
        if not schedule_name:
            return None
        if not refresh and self._cache_is_fresh() and self._cached_by_schedule_name:
            return self._cached_by_schedule_name.get(schedule_name)
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
        record = self.get_by_schedule_id(schedule_id, refresh=False) if schedule_id else None
        if record is None and schedule_name:
            record = self.get_by_schedule_name(schedule_name, refresh=False)
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
        record = self.get_by_schedule_id(schedule_id, refresh=False) if schedule_id else None
        if record is None and schedule_name:
            record = self.get_by_schedule_name(schedule_name, refresh=False)
        if record is None:
            return fallback
        return record.late_after_minutes

    def resolve_planned_end(
        self,
        *,
        schedule_id: str = "",
        schedule_name: str = "",
        event_date: date,
        fallback: str = "18:00",
    ) -> str:
        record = self.get_by_schedule_id(schedule_id, refresh=False) if schedule_id else None
        if record is None and schedule_name:
            record = self.get_by_schedule_name(schedule_name, refresh=False)
        if record is None:
            return self._parse_end_from_schedule_name(schedule_name) or fallback
        planned = record.planned_end_for(event_date)
        if planned:
            return planned
        return self._parse_end_from_schedule_name(record.schedule_name) or fallback

    def resolve_planned_minutes(
        self,
        *,
        schedule_id: str = "",
        schedule_name: str = "",
        event_date: date,
        fallback: int = 0,
    ) -> int:
        record = self.get_by_schedule_id(schedule_id, refresh=False) if schedule_id else None
        if record is None and schedule_name:
            record = self.get_by_schedule_name(schedule_name, refresh=False)
        normative_minutes = self._normative_minutes_from_schedule_name(
            record.schedule_name if record is not None else schedule_name
        )
        if normative_minutes > 0:
            return normative_minutes
        if record is None:
            return fallback
        planned = record.resolved_planned_minutes(event_date)
        if planned:
            return planned
        planned_start = record.planned_start_for(event_date)
        planned_end = record.planned_end_for(event_date) or self._parse_end_from_schedule_name(record.schedule_name)
        if not planned_start or not planned_end:
            return fallback
        try:
            start_dt = datetime.strptime(planned_start, "%H:%M")
            end_dt = datetime.strptime(planned_end, "%H:%M")
        except ValueError:
            return fallback
        total = int((end_dt - start_dt).total_seconds() // 60)
        if total <= 0:
            return fallback
        lunch_minutes = record.resolved_lunch_minutes()
        if lunch_minutes > 0:
            total = max(total - lunch_minutes, 0)
        return total or fallback

    def resolve_lunch_minutes(
        self,
        *,
        schedule_id: str = "",
        schedule_name: str = "",
        fallback: int = 0,
    ) -> int:
        record = self.get_by_schedule_id(schedule_id, refresh=False) if schedule_id else None
        if record is None and schedule_name:
            record = self.get_by_schedule_name(schedule_name, refresh=False)
        if record is None:
            return fallback
        return record.resolved_lunch_minutes() or fallback

    def resolve_lunch_window(
        self,
        *,
        schedule_id: str = "",
        schedule_name: str = "",
    ) -> tuple[str, str]:
        record = self.get_by_schedule_id(schedule_id, refresh=False) if schedule_id else None
        if record is None and schedule_name:
            record = self.get_by_schedule_name(schedule_name, refresh=False)
        if record is None:
            return "", ""
        return record.resolved_lunch_window()

    def resolve_lunch_mode(
        self,
        *,
        schedule_id: str = "",
        schedule_name: str = "",
        fallback: str = "deduct",
    ) -> str:
        record = self.get_by_schedule_id(schedule_id, refresh=False) if schedule_id else None
        if record is None and schedule_name:
            record = self.get_by_schedule_name(schedule_name, refresh=False)
        if record is None:
            return fallback
        mode = str(record.lunch_mode or "").strip().lower()
        if mode in {"fixed", "deduct", "none"}:
            return mode
        if record.lunch_start and record.lunch_end:
            return "fixed"
        if record.resolved_lunch_minutes() > 0:
            return "deduct"
        return fallback

    def _cache_is_fresh(self) -> bool:
        if self._cached_at is None:
            return False
        return datetime.now(timezone.utc) - self._cached_at <= timedelta(seconds=self.cache_ttl_seconds)

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
                    monday_end=self._pick(data, "Понедельник_окончание", "Понедельник_конец", "monday_end"),
                    tuesday_start=self._pick(data, "Вторник_начало", "tuesday_start"),
                    tuesday_end=self._pick(data, "Вторник_окончание", "Вторник_конец", "tuesday_end"),
                    wednesday_start=self._pick(data, "Среда_начало", "wednesday_start"),
                    wednesday_end=self._pick(data, "Среда_окончание", "Среда_конец", "wednesday_end"),
                    thursday_start=self._pick(data, "Четверг_начало", "thursday_start"),
                    thursday_end=self._pick(data, "Четверг_окончание", "Четверг_конец", "thursday_end"),
                    friday_start=self._pick(data, "Пятница_начало", "friday_start"),
                    friday_end=self._pick(data, "Пятница_окончание", "Пятница_конец", "friday_end"),
                    saturday_start=self._pick(data, "Суббота_начало", "saturday_start"),
                    saturday_end=self._pick(data, "Суббота_окончание", "Суббота_конец", "saturday_end"),
                    sunday_start=self._pick(data, "Воскресенье_начало", "sunday_start"),
                    sunday_end=self._pick(data, "Воскресенье_окончание", "Воскресенье_конец", "sunday_end"),
                    late_after_minutes=self._to_int(self._pick(data, "Допустимое_опоздание_мин", "late_after_minutes"), default=10),
                    lunch_start=self._pick(data, "Обед_с", "Обед_начало", "lunch_start"),
                    lunch_end=self._pick(data, "Обед_по", "Обед_окончание", "Обед_конец", "lunch_end"),
                    lunch_minutes=self._to_int(self._pick(data, "Обед_мин", "Обед_минут", "lunch_minutes"), default=0),
                    planned_minutes_per_day=self._to_int(
                        self._pick(data, "План_минут_в_день", "План_минут", "planned_minutes_per_day"),
                        default=0,
                    ),
                    lunch_mode=self._pick(data, "Тип_обеда", "lunch_mode"),
                    is_active=self._to_bool(self._pick(data, "Активен", "is_active"), default=True),
                    comment=self._pick(data, "Комментарий", "comment"),
                )
            )
        return records

    def _rebuild_indexes(self, records: List[GoogleSheetsScheduleRecord]) -> None:
        self._cached_by_schedule_id = {
            record.schedule_id: record
            for record in records
            if record.schedule_id
        }
        self._cached_by_schedule_name = {
            record.schedule_name: record
            for record in records
            if record.schedule_name
        }

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
    def _parse_end_from_schedule_name(schedule_name: str) -> str:
        if not schedule_name:
            return ""
        matches = re.findall(r"(\d{2}:\d{2})", schedule_name)
        if len(matches) >= 2:
            return matches[-1]
        return ""

    @staticmethod
    def _normative_minutes_from_schedule_name(schedule_name: str) -> int:
        normalized = str(schedule_name or "").strip().lower()
        if "девуш" in normalized:
            return 429
        if "парни" in normalized or "муж" in normalized:
            return 480
        return 0

    @staticmethod
    def _parse_lunch_window_from_text(value: str) -> tuple[str, str, int] | None:
        text = str(value or "")
        match = re.search(r"Обед\s*(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})", text, flags=re.IGNORECASE)
        if not match:
            return None
        start = match.group(1)
        end = match.group(2)
        try:
            start_dt = datetime.strptime(start, "%H:%M")
            end_dt = datetime.strptime(end, "%H:%M")
        except ValueError:
            return None
        minutes = max(int((end_dt - start_dt).total_seconds() // 60), 0)
        return start, end, minutes

    @staticmethod
    def _parse_lunch_window_from_schedule_name(value: str) -> tuple[str, str, int] | None:
        text = str(value or "")
        matches = re.findall(r"(\d{2}:\d{2})", text)
        if len(matches) < 4:
            return None
        lunch_start = matches[1]
        lunch_end = matches[2]
        try:
            start_dt = datetime.strptime(lunch_start, "%H:%M")
            end_dt = datetime.strptime(lunch_end, "%H:%M")
        except ValueError:
            return None
        minutes = int((end_dt - start_dt).total_seconds() // 60)
        if minutes <= 0:
            return None
        return lunch_start, lunch_end, minutes

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
