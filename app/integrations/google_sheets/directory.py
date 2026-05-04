from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Optional

from app.config import get_settings


GOOGLE_SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]


@dataclass(frozen=True)
class GoogleSheetsEmployeeRecord:
    employee_name: str = ""
    employee_user_id: str = ""
    manager_name: str = ""
    manager_user_id: str = ""
    department_name: str = ""
    role: str = "employee"
    is_active: bool = True


class GoogleSheetsDirectoryService:
    ROLE_ALIASES = {
        "employee": "employee",
        "сотрудник": "employee",
        "manager": "manager",
        "руководитель": "manager",
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
        values = self._fetch_values()
        records = self._parse_values(values)
        self._cached_records = records
        self._cached_at = datetime.now(timezone.utc)
        return list(records)

    def get_by_user_id(self, user_id: str, refresh: bool = False) -> Optional[GoogleSheetsEmployeeRecord]:
        if not user_id:
            return None
        for record in self.list_employees(refresh=refresh):
            if record.employee_user_id == user_id:
                return record
        return None

    def get_by_employee_name(self, employee_name: str, refresh: bool = False) -> Optional[GoogleSheetsEmployeeRecord]:
        if not employee_name:
            return None
        for record in self.list_employees(refresh=refresh):
            if record.employee_name == employee_name:
                return record
        return None

    def get_by_manager_user_id(self, manager_user_id: str, refresh: bool = False) -> List[GoogleSheetsEmployeeRecord]:
        if not manager_user_id:
            return []
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
                    employee_name=employee_name,
                    employee_user_id=employee_user_id,
                    manager_name=self._pick(data, "ФИО_руководителя", "manager_name"),
                    manager_user_id=self._pick(data, "ID_руководителя", "ID_руководителя_MAX", "manager_user_id"),
                    department_name=self._pick(data, "Подразделение", "department_name"),
                    role=self.normalize_role_value(self._pick(data, "Роль", "role") or "employee"),
                    is_active=self._to_bool(self._pick(data, "Работает", "Активен", "is_active"), default=True),
                )
            )
        return records

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
