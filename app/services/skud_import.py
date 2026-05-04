from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, time
from io import StringIO
from typing import Dict, List, Tuple

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
    unique_employees: int = 0
    period_start: str = ""
    period_end: str = ""
    samples: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class SkudImportService:
    def __init__(self) -> None:
        self.case_repository = AttendanceCaseRepository()
        self.approval_repository = ApprovalRepository()
        self.import_repository = SkudImportRepository()

    def import_csv(self, *, filename: str, content: bytes, created_by_user_id: str = "") -> SkudImportResult:
        text = content.decode("utf-8-sig")
        if self._looks_like_access_report(text):
            return self._import_access_report(
                filename=filename,
                text=text,
                created_by_user_id=created_by_user_id,
            )

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
            period_start=min_dt.date().isoformat() if min_dt else "",
            period_end=max_dt.date().isoformat() if max_dt else "",
            unique_employees=len({key[0] for key in first_entries.keys()}),
            total_rows=total_rows,
            created_cases=created_cases,
            error_rows=len(errors),
            samples_text="\n".join(samples),
        )
        return SkudImportResult(
            import_id=import_id,
            filename=filename,
            total_rows=total_rows,
            created_cases=created_cases,
            error_rows=len(errors),
            errors=errors,
        )

    def _import_access_report(self, *, filename: str, text: str, created_by_user_id: str) -> SkudImportResult:
        reader = csv.reader(StringIO(text), delimiter=";")
        rows = [row for row in reader]
        header_index = self._find_access_report_header_row(rows)
        if header_index is None:
            raise ValueError("Не удалось определить строку заголовков в отчете по проходам")

        data_start = header_index + 1
        while data_start < len(rows) and rows[data_start] and rows[data_start][0].strip() == "Ф.И.О":
            data_start += 1

        first_entries: Dict[Tuple[str, str], Dict[str, str]] = {}
        total_rows = 0
        errors: List[str] = []
        min_dt: datetime | None = None
        max_dt: datetime | None = None

        for row_number, row in enumerate(rows[data_start:], start=data_start + 1):
            if len(row) < 8:
                continue
            if not any(cell.strip() for cell in row):
                continue
            total_rows += 1
            try:
                employee_name = row[0].strip()
                department_name = row[3].strip()
                event_value = row[6].strip()
                zone_value = row[7].strip()
                dt_value = row[4].strip()
                if not employee_name or not dt_value:
                    continue
                if event_value != "Проход":
                    continue
                if zone_value != "Здание":
                    continue

                event_dt = datetime.strptime(dt_value, "%d.%m.%Y %H:%M:%S")
                if min_dt is None or event_dt < min_dt:
                    min_dt = event_dt
                if max_dt is None or event_dt > max_dt:
                    max_dt = event_dt
                key = (employee_name, event_dt.date().isoformat())
                current = first_entries.get(key)
                if current is None or event_dt.isoformat() < current["event_dt"]:
                    first_entries[key] = {
                        "employee_name": employee_name,
                        "department_name": department_name or "Не указано",
                        "event_date": event_dt.date().isoformat(),
                        "actual_start": event_dt.strftime("%H:%M"),
                        "event_dt": event_dt.isoformat(),
                    }
            except Exception as exc:
                errors.append(f"Строка {row_number}: {exc}")

        created_cases = 0
        samples: List[str] = []
        planned_time = time(hour=8, minute=30)
        for item in first_entries.values():
            actual_dt = datetime.fromisoformat(item["event_dt"])
            delay_minutes = int((actual_dt - datetime.combine(actual_dt.date(), planned_time)).total_seconds() // 60)
            if delay_minutes <= 0:
                continue
            if len(samples) < 5:
                samples.append(
                    "{name} | {date} | {time} | +{delay} мин".format(
                        name=item["employee_name"],
                        date=item["event_date"],
                        time=item["actual_start"],
                        delay=delay_minutes,
                    )
                )
            self.case_repository.create_case(
                employee_name=item["employee_name"],
                department_name=item["department_name"],
                case_type=AttendanceCaseType.LATE.value,
                status=AttendanceCaseStatus.AWAITING_EMPLOYEE_REASON.value,
                event_date=item["event_date"],
                planned_start="08:30",
                actual_start=item["actual_start"],
                delay_minutes=delay_minutes,
                employee_reason="",
                source="skud_report",
            )
            created_cases += 1

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
            unique_employees=len({key[0] for key in first_entries.keys()}),
            period_start=min_dt.date().isoformat() if min_dt else "",
            period_end=max_dt.date().isoformat() if max_dt else "",
            samples=samples,
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

    @staticmethod
    def _looks_like_access_report(text: str) -> bool:
        return "Отчет по проходам" in text and "Ф.И.О" in text and "Событие" in text

    @staticmethod
    def _find_access_report_header_row(rows: List[List[str]]) -> int | None:
        for index, row in enumerate(rows):
            if not row:
                continue
            values = [cell.strip() for cell in row]
            if "Ф.И.О" in values and "Событие" in values:
                return index
        return None
