from __future__ import annotations

import csv
from dataclasses import dataclass, field
from io import StringIO
from typing import Dict, List

from app.repositories.employee_directory_repository import EmployeeDirectoryRepository


@dataclass
class EmployeeDirectoryImportResult:
    total_rows: int
    upserted_rows: int
    errors: List[str] = field(default_factory=list)


class EmployeeDirectoryImportService:
    def __init__(self) -> None:
        self.repository = EmployeeDirectoryRepository()

    def import_csv(self, content: bytes) -> EmployeeDirectoryImportResult:
        text = content.decode("utf-8-sig")
        sample = text[:1024]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,")
        except csv.Error:
            dialect = csv.excel
            dialect.delimiter = ";"

        reader = csv.DictReader(StringIO(text), dialect=dialect)
        total_rows = 0
        upserted_rows = 0
        errors: List[str] = []
        rows: List[Dict[str, str]] = []

        for row_number, raw_row in enumerate(reader, start=2):
            if not any((value or "").strip() for value in raw_row.values()):
                continue
            total_rows += 1
            try:
                normalized = self._normalize_row(raw_row)
                if normalized.get("employee_user_id"):
                    rows.append(normalized)
                    upserted_rows += 1
            except Exception as exc:
                errors.append(f"Строка {row_number}: {exc}")

        if rows:
            self.repository.upsert_many(rows)

        return EmployeeDirectoryImportResult(
            total_rows=total_rows,
            upserted_rows=upserted_rows,
            errors=errors,
        )

    def _normalize_row(self, raw_row: Dict[str, str]) -> Dict[str, str]:
        row = {str(key).strip(): (value or "").strip() for key, value in raw_row.items() if key is not None}
        return {
            "employee_name": self._pick(row, "ФИО", "employee_name", "Сотрудник"),
            "employee_user_id": self._pick(row, "ID_пользователя_MAX", "employee_user_id", "MAX_ID", "ID MAX"),
            "manager_name": self._pick(row, "ФИО_руководителя", "manager_name", "Руководитель"),
            "manager_user_id": self._pick(row, "ID_руководителя_MAX", "manager_user_id", "manager_user_id_max"),
            "department_name": self._pick(row, "Подразделение", "department_name", "Отдел"),
            "office": self._pick(row, "Кабинет", "office"),
            "schedule_name": self._pick(row, "График", "schedule_name"),
            "schedule_id": self._pick(row, "ID_графика", "schedule_id"),
            "role": self._pick(row, "Роль", "role") or "employee",
            "is_active": self._pick(row, "Работает", "is_active") or "Да",
        }

    @staticmethod
    def _pick(row: Dict[str, str], *keys: str) -> str:
        for key in keys:
            value = row.get(key)
            if value:
                return value
        return ""
