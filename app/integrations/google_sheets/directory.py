from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Iterable, List, Optional

from app.config import get_settings


GOOGLE_SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]


@dataclass(frozen=True)
class GoogleSheetsEmployeeRecord:
    employee_id: str = ""
    employee_name: str = ""
    employee_user_id: str = ""
    manager_name: str = ""
    manager_user_id: str = ""
    department_name: str = ""
    schedule_name: str = ""
    schedule_id: str = ""
    office: str = ""
    role: str = "employee"
    is_active: bool = True


class GoogleSheetsDirectoryService:
    ROLE_ALIASES = {
        "employee": "employee",
        "сотрудник": "employee",
        "manager": "manager",
        "руководитель": "manager",
        "начальник отдела": "manager",
        "начальник_отдела": "manager",
        "зам руководителя": "manager",
        "зам_руководителя": "manager",
        "зам.руководителя": "manager",
        "зам. руководителя": "manager",
        "security": "security",
        "безопасность": "security",
        "hr": "hr",
        "кадры": "hr",
        "админ": "admin",
        "administrator": "admin",
        "администратор": "admin",
        "admin": "admin",
        "top_manager": "top_manager",
        "top": "top_manager",
        "топ_руководитель": "top_manager",
        "топ-руководитель": "top_manager",
    }

    def __init__(
        self,
        spreadsheet_id: str | None = None,
        service_account_file: str | None = None,
        employee_range: str | None = None,
        cache_ttl_seconds: int = 300,
    ) -> None:
        settings = get_settings()
        self.spreadsheet_id = spreadsheet_id or settings.google_sheets_spreadsheet_id
        self.service_account_file = service_account_file or settings.google_service_account_file
        self.employee_range = employee_range or settings.google_sheets_employee_range
        self.cache_ttl_seconds = cache_ttl_seconds or settings.google_sheets_cache_ttl_seconds
        self._cached_records: List[GoogleSheetsEmployeeRecord] = []
        self._cached_at: datetime | None = None
        self._cached_by_user_id: dict[str, GoogleSheetsEmployeeRecord] = {}
        self._cached_by_employee_name: dict[str, GoogleSheetsEmployeeRecord] = {}
        self._cached_by_normalized_name: dict[str, GoogleSheetsEmployeeRecord] = {}
        self._cached_by_prefix_name: dict[tuple[str, str, str], GoogleSheetsEmployeeRecord] = {}
        self._cached_by_manager_user_id: dict[str, List[GoogleSheetsEmployeeRecord]] = {}
        self.logger = logging.getLogger(__name__)

    @classmethod
    def from_settings(cls) -> "GoogleSheetsDirectoryService":
        settings = get_settings()
        return cls(
            spreadsheet_id=settings.google_sheets_spreadsheet_id,
            service_account_file=settings.google_service_account_file,
            employee_range=settings.google_sheets_employee_range,
            cache_ttl_seconds=settings.google_sheets_cache_ttl_seconds,
        )

    def is_configured(self) -> bool:
        return bool(self.spreadsheet_id and self.service_account_file and Path(self.service_account_file).exists())

    def list_employees(self, refresh: bool = False) -> List[GoogleSheetsEmployeeRecord]:
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
                "Google Sheets directory loaded records=%s refresh=%s elapsed_ms=%.1f",
                len(records),
                refresh,
                (perf_counter() - started_at) * 1000,
            )
            return list(records)
        except Exception as exc:
            if self._cached_records:
                self.logger.warning(
                    "Google Sheets directory fetch failed, using cached records=%s refresh=%s elapsed_ms=%.1f error=%s",
                    len(self._cached_records),
                    refresh,
                    (perf_counter() - started_at) * 1000,
                    exc,
                )
                return list(self._cached_records)
            self.logger.warning(
                "Google Sheets directory fetch failed and cache is empty refresh=%s elapsed_ms=%.1f error=%s",
                refresh,
                (perf_counter() - started_at) * 1000,
                exc,
            )
            return []

    def get_by_user_id(self, user_id: str, refresh: bool = False) -> Optional[GoogleSheetsEmployeeRecord]:
        if not user_id:
            return None
        if not refresh and self._cache_is_fresh() and self._cached_by_user_id:
            return self._cached_by_user_id.get(user_id)
        records = self.list_employees(refresh=refresh)
        for record in records:
            if record.employee_user_id == user_id:
                return record
        return None

    def get_by_employee_name(self, employee_name: str, refresh: bool = False) -> Optional[GoogleSheetsEmployeeRecord]:
        if not employee_name:
            return None
        if not refresh and self._cache_is_fresh() and self._cached_by_employee_name:
            return self._match_employee_name_from_indexes(employee_name)
        self.list_employees(refresh=refresh)
        return self._match_employee_name_from_indexes(employee_name)

    def get_by_manager_user_id(self, manager_user_id: str, refresh: bool = False) -> List[GoogleSheetsEmployeeRecord]:
        if not manager_user_id:
            return []
        if not refresh and self._cache_is_fresh() and self._cached_by_manager_user_id:
            return list(self._cached_by_manager_user_id.get(manager_user_id, []))
        return [
            record
            for record in self.list_employees(refresh=refresh)
            if record.manager_user_id == manager_user_id and record.is_active
        ]

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
                range=self.employee_range,
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

    def _parse_values(self, values: List[List[str]]) -> List[GoogleSheetsEmployeeRecord]:
        if not values:
            return []

        headers = [self._normalize_cell(cell) for cell in values[0]]
        records: List[GoogleSheetsEmployeeRecord] = []
        for row in values[1:]:
            if not any(self._normalize_cell(cell) for cell in row):
                continue
            data = {
                headers[index]: self._normalize_cell(cell)
                for index, cell in enumerate(row)
                if index < len(headers) and headers[index]
            }
            employee_name = self._pick(data, "ФИО", "employee_name")
            employee_user_id = self._pick(data, "ID_пользователя_MAX", "employee_user_id", "MAX_ID")
            if not employee_user_id and not employee_name:
                continue
            records.append(
                GoogleSheetsEmployeeRecord(
                    employee_id=self._pick(data, "ID_сотрудника", "employee_id"),
                    employee_name=employee_name,
                    employee_user_id=employee_user_id,
                    manager_name=self._pick(data, "ФИО_руководителя", "manager_name"),
                    manager_user_id=self._pick(data, "ID_руководителя", "ID_руководителя_MAX", "manager_user_id"),
                    department_name=self._pick(data, "Подразделение", "department_name"),
                    schedule_name=self._pick(data, "График", "schedule_name"),
                    schedule_id=self._pick(data, "ID_графика", "schedule_id"),
                    office=self._pick(data, "Кабинет", "office"),
                    role=self.normalize_role_value(self._pick(data, "Роль", "role") or "employee"),
                    is_active=self._to_bool(self._pick(data, "Работает", "Активен", "is_active"), default=True),
                )
            )
        return records

    def _rebuild_indexes(self, records: List[GoogleSheetsEmployeeRecord]) -> None:
        self._cached_by_user_id = {
            record.employee_user_id: record
            for record in records
            if record.employee_user_id
        }
        self._cached_by_employee_name = {
            record.employee_name: record
            for record in records
            if record.employee_name
        }
        normalized_index: dict[str, list[GoogleSheetsEmployeeRecord]] = {}
        prefix_index: dict[tuple[str, str, str], list[GoogleSheetsEmployeeRecord]] = {}
        for record in records:
            if not record.employee_name:
                continue
            normalized_index.setdefault(self._normalize_employee_name(record.employee_name), []).append(record)
            prefix_index.setdefault(self._employee_name_prefix(record.employee_name), []).append(record)
        self._cached_by_normalized_name = {
            key: matched[0]
            for key, matched in normalized_index.items()
            if key and len(matched) == 1
        }
        self._cached_by_prefix_name = {
            key: matched[0]
            for key, matched in prefix_index.items()
            if key and len(matched) == 1
        }
        manager_index: dict[str, List[GoogleSheetsEmployeeRecord]] = {}
        for record in records:
            if not record.manager_user_id or not record.is_active:
                continue
            manager_index.setdefault(record.manager_user_id, []).append(record)
        self._cached_by_manager_user_id = manager_index

    def _match_employee_name_from_indexes(self, employee_name: str) -> Optional[GoogleSheetsEmployeeRecord]:
        exact = self._cached_by_employee_name.get(employee_name)
        if exact is not None:
            return exact
        normalized = self._cached_by_normalized_name.get(self._normalize_employee_name(employee_name))
        if normalized is not None:
            return normalized
        return self._cached_by_prefix_name.get(self._employee_name_prefix(employee_name))

    @classmethod
    def normalize_role_value(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        return cls.ROLE_ALIASES.get(normalized, normalized or "employee")

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
    def _normalize_employee_name(value: str) -> str:
        normalized = str(value or "").strip().lower().replace("ё", "е")
        return re.sub(r"[^a-zа-я0-9]+", "", normalized)

    @classmethod
    def _employee_name_prefix(cls, value: str) -> tuple[str, str, str]:
        normalized = str(value or "").strip().lower().replace("ё", "е")
        parts = [part for part in re.split(r"\s+", normalized) if part]
        if not parts:
            return ("", "", "")
        surname = re.sub(r"[^a-zа-я0-9]+", "", parts[0])
        first_name = re.sub(r"[^a-zа-я0-9]+", "", parts[1]) if len(parts) > 1 else ""
        patronymic = re.sub(r"[^a-zа-я0-9]+", "", parts[2]) if len(parts) > 2 else ""
        return (surname, first_name, patronymic[:5])
