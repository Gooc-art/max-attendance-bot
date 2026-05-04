from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO
from typing import Dict, List

from app.domain.enums import ApprovalStatus, AttendanceCaseStatus, AttendanceCaseType
from app.repositories.approval_repository import ApprovalRepository
from app.repositories.attendance_case_repository import AttendanceCaseRepository
from app.repositories.skud_import_repository import SkudImportRepository


CASE_TYPE_MAP = {
    "late": AttendanceCaseType.LATE.value,
    "опоздание": AttendanceCaseType.LATE.value,
    "absent": AttendanceCaseType.ABSENT.value,
    "неявка": AttendanceCaseType.ABSENT.value,
}


@dataclass
class SkudImportResult:
    import_id: int
    filename: str
    total_rows: int
    created_cases: int
    error_rows: int
    errors: List[str]


class SkudImportService:
    def __init__(self) -> None:
        self.case_repository = AttendanceCaseRepository()
        self.approval_repository = ApprovalRepository()
        self.import_repository = SkudImportRepository()

    def import_csv(self, *, filename: str, content: bytes, created_by_user_id: str = "") -> SkudImportResult:
        text = content.decode("utf-8-sig")
        sample = text[:1024]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,")
        except csv.Error:
            dialect = csv.excel
            dialect.delimiter = ";"

        reader = csv.DictReader(StringIO(text), dialect=dialect)
        total_rows = 0
        created_cases = 0
        errors: List[str] = []

        for row_number, raw_row in enumerate(reader, start=2):
            if not any((value or "").strip() for value in raw_row.values()):
                continue
            total_rows += 1
            try:
                normalized = self._normalize_row(raw_row)
                case_id = self.case_repository.create_case(**normalized)
                created_cases += 1
                if normalized["employee_reason"] and normalized["manager_user_id"]:
                    self.approval_repository.create_if_missing(
                        case_id=case_id,
                        manager_user_id=normalized["manager_user_id"],
                        manager_name=normalized["manager_name"] or "Руководитель",
                        status=ApprovalStatus.PENDING.value,
                    )
            except Exception as exc:
                errors.append(f"Строка {row_number}: {exc}")

        import_id = self.import_repository.create(
            filename=filename,
            created_by_user_id=created_by_user_id,
            status="completed" if not errors else "completed_with_errors",
            total_rows=total_rows,
            created_cases=created_cases,
            error_rows=len(errors),
        )
        return SkudImportResult(
            import_id=import_id,
            filename=filename,
            total_rows=total_rows,
            created_cases=created_cases,
            error_rows=len(errors),
            errors=errors,
        )

    def _normalize_row(self, raw_row: Dict[str, str]) -> Dict[str, object]:
        row = {str(key).strip(): (value or "").strip() for key, value in raw_row.items() if key is not None}

        employee_name = self._pick(row, "employee_name", "ФИО")
        if not employee_name:
            raise ValueError("не заполнено ФИО")

        raw_case_type = self._pick(row, "case_type", "Тип_случая", "Тип")
        case_type = CASE_TYPE_MAP.get(raw_case_type.lower())
        if not case_type:
            raise ValueError(f"неизвестный тип случая: {raw_case_type or '-'}")

        planned_start = self._pick(row, "planned_start", "Плановое_время", "План")
        event_date = self._pick(row, "event_date", "Дата")
        if not planned_start or not event_date:
            raise ValueError("не заполнены дата или плановое время")

        actual_start = self._pick(row, "actual_start", "Фактическое_время", "Факт") or "-"
        employee_reason = self._pick(row, "employee_reason", "Причина")
        status = (
            AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value
            if employee_reason
            else AttendanceCaseStatus.AWAITING_EMPLOYEE_REASON.value
        )

        delay_text = self._pick(row, "delay_minutes", "Минут_опоздания", "Опоздание_мин")
        try:
            delay_minutes = int(delay_text or "0")
        except ValueError as exc:
            raise ValueError(f"некорректное значение минут опоздания: {delay_text}") from exc

        return {
            "employee_user_id": self._pick(row, "employee_user_id", "ID_пользователя_MAX"),
            "employee_name": employee_name,
            "department_name": self._pick(row, "department_name", "Подразделение") or "Не указано",
            "manager_user_id": self._pick(row, "manager_user_id", "ID_руководителя_MAX"),
            "manager_name": self._pick(row, "manager_name", "ФИО_руководителя"),
            "case_type": case_type,
            "status": status,
            "event_date": event_date,
            "planned_start": planned_start,
            "actual_start": actual_start,
            "delay_minutes": delay_minutes,
            "employee_reason": employee_reason,
            "source": "skud_import",
        }

    @staticmethod
    def _pick(row: Dict[str, str], *keys: str) -> str:
        for key in keys:
            value = row.get(key)
            if value:
                return value
        return ""
