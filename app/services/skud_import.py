from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime, time
from io import StringIO
from typing import Dict, List, Tuple

from app.domain.enums import ApprovalStatus, AttendanceCaseStatus, AttendanceCaseType
from app.integrations.google_sheets.directory import GoogleSheetsDirectoryService
from app.integrations.google_sheets.schedules import GoogleSheetsScheduleService
from app.repositories.approval_repository import ApprovalRepository
from app.repositories.attendance_day_record_repository import AttendanceDayRecordRepository
from app.repositories.employee_directory_repository import EmployeeDirectoryRepository
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
    arrivals_early: int = 0
    arrivals_on_time: int = 0
    arrivals_late: int = 0
    departures_early: int = 0
    departures_on_time: int = 0
    departures_late: int = 0
    samples: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class SkudImportService:
    def __init__(self) -> None:
        self.case_repository = AttendanceCaseRepository()
        self.approval_repository = ApprovalRepository()
        self.google_directory_service = GoogleSheetsDirectoryService.from_settings()
        self.google_schedule_service = GoogleSheetsScheduleService.from_settings()
        self.employee_directory_repository = EmployeeDirectoryRepository()
        self.day_record_repository = AttendanceDayRecordRepository()
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
        unique_employees = set()
        min_dt: datetime | None = None
        max_dt: datetime | None = None
        samples: List[str] = []

        for row_number, raw_row in enumerate(reader, start=2):
            if not any((value or "").strip() for value in raw_row.values()):
                continue
            total_rows += 1
            try:
                normalized = self._normalize_row(raw_row)
                case_id = self.case_repository.create_case(**normalized)
                created_cases += 1
                unique_employees.add(normalized["employee_name"])
                event_dt = self._parse_event_date(str(normalized["event_date"]))
                if event_dt is not None:
                    if min_dt is None or event_dt < min_dt:
                        min_dt = event_dt
                    if max_dt is None or event_dt > max_dt:
                        max_dt = event_dt
                if len(samples) < 5:
                    samples.append(
                        "{name} | {date} | {planned} | {status}".format(
                            name=normalized["employee_name"],
                            date=normalized["event_date"],
                            planned=normalized["planned_start"],
                            status=normalized["status"],
                        )
                    )
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
            unique_employees=len(unique_employees),
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
            unique_employees=len(unique_employees),
            period_start=min_dt.date().isoformat() if min_dt else "",
            period_end=max_dt.date().isoformat() if max_dt else "",
            samples=samples,
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

        daily_records: Dict[Tuple[str, str], Dict[str, object]] = {}
        total_rows = 0
        errors: List[str] = []
        min_dt: datetime | None = None
        max_dt: datetime | None = None
        arrivals_early = 0
        arrivals_on_time = 0
        arrivals_late = 0
        departures_early = 0
        departures_on_time = 0
        departures_late = 0

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

                event_dt = datetime.strptime(dt_value, "%d.%m.%Y %H:%M:%S")
                if min_dt is None or event_dt < min_dt:
                    min_dt = event_dt
                if max_dt is None or event_dt > max_dt:
                    max_dt = event_dt
                employee_directory = self._resolve_directory_record(employee_name)
                planned_start = self._resolve_planned_start(employee_directory, event_dt.date())
                planned_end = self._resolve_planned_end(employee_directory, event_dt.date())
                if not planned_start and not planned_end:
                    continue
                key = (employee_name, event_dt.date().isoformat())
                current = daily_records.get(key)
                if current is None:
                    current = {
                        "record_key": self._build_record_key(employee_directory, employee_name, event_dt.date().isoformat()),
                        "employee_name": employee_name,
                        "department_name": (
                            employee_directory["department_name"] if employee_directory and employee_directory["department_name"] else department_name
                        )
                        or "Не указано",
                        "event_date": event_dt.date().isoformat(),
                        "employee_user_id": employee_directory["employee_user_id"] if employee_directory else "",
                        "manager_user_id": employee_directory["manager_user_id"] if employee_directory else "",
                        "manager_name": employee_directory["manager_name"] if employee_directory else "",
                        "schedule_name": employee_directory.get("schedule_name", "") if employee_directory else "",
                        "schedule_id": employee_directory.get("schedule_id", "") if employee_directory else "",
                        "planned_start": planned_start or "",
                        "planned_end": planned_end or "",
                        "first_entry_dt": "",
                        "last_exit_dt": "",
                        "total_passes": 0,
                    }
                    daily_records[key] = current
                current["total_passes"] = int(current.get("total_passes", 0) or 0) + 1
                is_entry = zone_value == "Здание"
                is_exit = zone_value == "Внешний мир"
                if is_entry:
                    current_first = str(current.get("first_entry_dt", ""))
                    if not current_first or event_dt.isoformat() < current_first:
                        current["first_entry_dt"] = event_dt.isoformat()
                if is_exit:
                    current_last = str(current.get("last_exit_dt", ""))
                    if not current_last or event_dt.isoformat() > current_last:
                        current["last_exit_dt"] = event_dt.isoformat()
            except Exception as exc:
                errors.append(f"Строка {row_number}: {exc}")

        created_cases = 0
        samples: List[str] = []
        attendance_rows: List[Dict[str, object]] = []
        for item in daily_records.values():
            planned_start = str(item.get("planned_start", "")).strip()
            planned_end = str(item.get("planned_end", "")).strip()
            event_date_str = str(item.get("event_date", "")).strip()
            event_date = self._parse_event_date(event_date_str)
            if event_date is None:
                continue

            arrival_dt = self._parse_iso_datetime(str(item.get("first_entry_dt", "")).strip())
            departure_dt = self._parse_iso_datetime(str(item.get("last_exit_dt", "")).strip())
            arrival_status = ""
            arrival_delta = 0
            departure_status = ""
            departure_delta = 0

            if arrival_dt and planned_start:
                arrival_status, arrival_delta = self._classify_arrival(
                    arrival_dt=arrival_dt,
                    planned_start=planned_start,
                    grace_minutes=self._resolve_late_after_minutes(item),
                )
                if arrival_status == "early":
                    arrivals_early += 1
                elif arrival_status == "on_time":
                    arrivals_on_time += 1
                else:
                    arrivals_late += 1
                    if len(samples) < 5:
                        samples.append(
                            "{name} | {date} | {time} | +{delay} мин".format(
                                name=item["employee_name"],
                                date=event_date_str,
                                time=arrival_dt.strftime("%H:%M"),
                                delay=arrival_delta,
                            )
                        )
                    self.case_repository.create_case(
                        employee_user_id=str(item.get("employee_user_id", "")),
                        employee_name=str(item["employee_name"]),
                        department_name=str(item["department_name"]),
                        manager_user_id=str(item.get("manager_user_id", "")),
                        manager_name=str(item.get("manager_name", "")),
                        case_type=AttendanceCaseType.LATE.value,
                        status=AttendanceCaseStatus.AWAITING_EMPLOYEE_REASON.value,
                        event_date=event_date_str,
                        planned_start=planned_start,
                        actual_start=arrival_dt.strftime("%H:%M"),
                        delay_minutes=arrival_delta,
                        employee_reason="",
                        source="skud_report",
                    )
                    created_cases += 1

            if departure_dt and planned_end:
                departure_status, departure_delta = self._classify_departure(
                    departure_dt=departure_dt,
                    planned_end=planned_end,
                )
                if departure_status == "early":
                    departures_early += 1
                elif departure_status == "on_time":
                    departures_on_time += 1
                else:
                    departures_late += 1

            attendance_rows.append(
                {
                    "record_key": str(item.get("record_key", "")),
                    "employee_user_id": str(item.get("employee_user_id", "")),
                    "employee_name": str(item.get("employee_name", "")),
                    "department_name": str(item.get("department_name", "")),
                    "manager_user_id": str(item.get("manager_user_id", "")),
                    "manager_name": str(item.get("manager_name", "")),
                    "schedule_name": str(item.get("schedule_name", "")),
                    "schedule_id": str(item.get("schedule_id", "")),
                    "event_date": event_date_str,
                    "planned_start": planned_start,
                    "planned_end": planned_end,
                    "first_entry_time": arrival_dt.strftime("%H:%M") if arrival_dt else "",
                    "arrival_status": arrival_status,
                    "arrival_delta_minutes": arrival_delta,
                    "last_exit_time": departure_dt.strftime("%H:%M") if departure_dt else "",
                    "departure_status": departure_status,
                    "departure_delta_minutes": departure_delta,
                    "total_passes": int(item.get("total_passes", 0) or 0),
                    "source": "skud_report",
                }
            )

        self.day_record_repository.upsert_many(attendance_rows)

        import_id = self.import_repository.create(
            filename=filename,
            created_by_user_id=created_by_user_id,
            status="completed" if not errors else "completed_with_errors",
            period_start=min_dt.date().isoformat() if min_dt else "",
            period_end=max_dt.date().isoformat() if max_dt else "",
            unique_employees=len({key[0] for key in daily_records.keys()}),
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
            unique_employees=len({key[0] for key in daily_records.keys()}),
            period_start=min_dt.date().isoformat() if min_dt else "",
            period_end=max_dt.date().isoformat() if max_dt else "",
            arrivals_early=arrivals_early,
            arrivals_on_time=arrivals_on_time,
            arrivals_late=arrivals_late,
            departures_early=departures_early,
            departures_on_time=departures_on_time,
            departures_late=departures_late,
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

    def _resolve_directory_record(self, employee_name: str) -> Dict[str, str]:
        google_record = self.google_directory_service.get_by_employee_name(employee_name)
        local_record = self.employee_directory_repository.get_by_employee_name(employee_name)

        return {
            "employee_name": self._merge_directory_value(
                google_record.employee_name if google_record else "",
                local_record.employee_name if local_record else "",
                fallback=employee_name,
            ),
            "employee_user_id": self._merge_directory_value(
                google_record.employee_user_id if google_record else "",
                local_record.employee_user_id if local_record else "",
            ),
            "manager_name": self._merge_directory_value(
                google_record.manager_name if google_record else "",
                local_record.manager_name if local_record else "",
            ),
            "manager_user_id": self._merge_directory_value(
                google_record.manager_user_id if google_record else "",
                local_record.manager_user_id if local_record else "",
            ),
            "department_name": self._merge_directory_value(
                google_record.department_name if google_record else "",
                local_record.department_name if local_record else "",
            ),
            "schedule_name": self._merge_directory_value(
                google_record.schedule_name if google_record else "",
                "",
            ),
            "schedule_id": self._merge_directory_value(
                google_record.schedule_id if google_record else "",
                "",
            ),
            "role": self._merge_directory_value(
                google_record.role if google_record else "",
                local_record.role if local_record else "",
                fallback="employee",
            ),
        }

    @staticmethod
    def _merge_directory_value(primary: str, secondary: str, fallback: str = "") -> str:
        return primary or secondary or fallback

    def _resolve_planned_start(self, employee_directory: Dict[str, str], event_date: date) -> str | None:
        schedule_id = employee_directory.get("schedule_id", "")
        schedule_name = employee_directory.get("schedule_name", "")
        planned_start = self.google_schedule_service.resolve_planned_start(
            schedule_id=schedule_id,
            schedule_name=schedule_name,
            event_date=event_date,
            fallback="08:30",
        )
        return planned_start or None

    def _resolve_late_after_minutes(self, employee_directory: Dict[str, str]) -> int:
        schedule_id = employee_directory.get("schedule_id", "")
        schedule_name = employee_directory.get("schedule_name", "")
        return self.google_schedule_service.resolve_late_after_minutes(
            schedule_id=schedule_id,
            schedule_name=schedule_name,
            fallback=10,
        )

    def _resolve_planned_end(self, employee_directory: Dict[str, str], event_date: date) -> str:
        schedule_id = employee_directory.get("schedule_id", "")
        schedule_name = employee_directory.get("schedule_name", "")
        planned_end = self.google_schedule_service.resolve_planned_end(
            schedule_id=schedule_id,
            schedule_name=schedule_name,
            event_date=event_date,
            fallback="18:00",
        )
        return planned_end or ""

    @staticmethod
    def _parse_time(value: str) -> time:
        for fmt in ("%H:%M", "%H:%M:%S"):
            try:
                return datetime.strptime(value, fmt).time()
            except ValueError:
                continue
        return time(hour=8, minute=30)

    @staticmethod
    def _parse_event_date(value: str) -> datetime | None:
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%Y %H:%M:%S"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_iso_datetime(value: str) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    @staticmethod
    def _classify_arrival(*, arrival_dt: datetime, planned_start: str, grace_minutes: int) -> tuple[str, int]:
        planned_time = SkudImportService._parse_time(planned_start)
        planned_dt = datetime.combine(arrival_dt.date(), planned_time)
        delta_minutes = int((arrival_dt - planned_dt).total_seconds() // 60)
        if delta_minutes < 0:
            return "early", delta_minutes
        if delta_minutes <= grace_minutes:
            return "on_time", delta_minutes
        return "late", delta_minutes

    @staticmethod
    def _classify_departure(*, departure_dt: datetime, planned_end: str) -> tuple[str, int]:
        planned_time = SkudImportService._parse_time(planned_end)
        planned_dt = datetime.combine(departure_dt.date(), planned_time)
        delta_minutes = int((departure_dt - planned_dt).total_seconds() // 60)
        if delta_minutes < 0:
            return "early", delta_minutes
        if delta_minutes == 0:
            return "on_time", delta_minutes
        return "late", delta_minutes

    @staticmethod
    def _build_record_key(employee_directory: Dict[str, str], employee_name: str, event_date: str) -> str:
        employee_user_id = employee_directory.get("employee_user_id", "")
        if employee_user_id:
            return f"user:{employee_user_id}:{event_date}"
        return f"name:{employee_name}:{event_date}"
