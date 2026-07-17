from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
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
from app.repositories.substitution_repository import SubstitutionRepository


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
        self.substitution_repository = SubstitutionRepository()

    def import_csv(
        self,
        *,
        filename: str,
        content: bytes,
        created_by_user_id: str = "",
        create_cases: bool = True,
    ) -> SkudImportResult:
        text = content.decode("utf-8-sig")
        if self._looks_like_access_report(text):
            return self._import_access_report(
                filename=filename,
                text=text,
                created_by_user_id=created_by_user_id,
                create_cases=create_cases,
            )
        if self._looks_like_employee_summary_report(text):
            return self._import_employee_summary_report(
                filename=filename,
                text=text,
                created_by_user_id=created_by_user_id,
                create_cases=create_cases,
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

    def _import_access_report(
        self,
        *,
        filename: str,
        text: str,
        created_by_user_id: str,
        create_cases: bool = True,
    ) -> SkudImportResult:
        reader = csv.reader(StringIO(text), delimiter=";")
        rows = [row for row in reader]
        header_index = self._find_access_report_header_row(rows)
        if header_index is None:
            raise ValueError("Не удалось определить строку заголовков в отчете по проходам")

        headers = [cell.strip() for cell in rows[header_index]]
        data_start = header_index + 1
        while data_start < len(rows) and rows[data_start] and rows[data_start][0].strip() in {"Ф.И.О", "Фирма"}:
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
                parsed_row = self._parse_access_report_row(headers, row)
                if parsed_row is None:
                    continue

                employee_name, department_name, dt_value, direction = parsed_row
                event_dt = self._parse_event_date(dt_value)
                if event_dt is None:
                    raise ValueError("не удалось распознать дату и время")
                if min_dt is None or event_dt < min_dt:
                    min_dt = event_dt
                if max_dt is None or event_dt > max_dt:
                    max_dt = event_dt
                employee_directory = self._resolve_directory_record(employee_name)
                if not self._should_track_employee(employee_directory):
                    continue
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
                        "events": [],
                        "first_entry_dt": "",
                        "last_exit_dt": "",
                        "total_passes": 0,
                    }
                    daily_records[key] = current
                current["total_passes"] = int(current.get("total_passes", 0) or 0) + 1
                current.setdefault("events", []).append(
                    {
                        "dt": event_dt.isoformat(),
                        "zone": direction,
                        "kind": direction,
                    }
                )
                if direction == "entry":
                    current_first = str(current.get("first_entry_dt", ""))
                    if not current_first or event_dt.isoformat() < current_first:
                        current["first_entry_dt"] = event_dt.isoformat()
                if direction == "exit":
                    current_last = str(current.get("last_exit_dt", ""))
                    if not current_last or event_dt.isoformat() > current_last:
                        current["last_exit_dt"] = event_dt.isoformat()
            except Exception as exc:
                errors.append(f"Строка {row_number}: {exc}")

        return self._finalize_daily_records(
            filename=filename,
            created_by_user_id=created_by_user_id,
            create_cases=create_cases,
            total_rows=total_rows,
            errors=errors,
            min_dt=min_dt,
            max_dt=max_dt,
            daily_records=daily_records,
        )

    def _import_employee_summary_report(
        self,
        *,
        filename: str,
        text: str,
        created_by_user_id: str,
        create_cases: bool = True,
    ) -> SkudImportResult:
        rows = [row for row in csv.reader(StringIO(text), delimiter=";")]
        header_index = self._find_employee_summary_header_row(rows)
        if header_index is None:
            raise ValueError("Не удалось определить строку заголовков в отчете по сотруднику")

        headers = [cell.strip() for cell in rows[header_index]]
        total_rows = 0
        errors: List[str] = []
        min_dt: datetime | None = None
        max_dt: datetime | None = None
        daily_records: Dict[Tuple[str, str], Dict[str, object]] = {}

        for row_number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
            if not any((cell or "").strip() for cell in row):
                continue
            total_rows += 1
            try:
                record = self._parse_employee_summary_row(headers, row)
                if record is None:
                    continue
                event_dt = self._parse_event_date(str(record["event_date"]))
                if event_dt is None:
                    raise ValueError("не заполнена или не распознана дата")
                if min_dt is None or event_dt < min_dt:
                    min_dt = event_dt
                if max_dt is None or event_dt > max_dt:
                    max_dt = event_dt
                daily_records[(str(record["employee_name"]), str(record["event_date"]))] = record
            except Exception as exc:
                errors.append(f"Строка {row_number}: {exc}")

        return self._finalize_daily_records(
            filename=filename,
            created_by_user_id=created_by_user_id,
            create_cases=create_cases,
            total_rows=total_rows,
            errors=errors,
            min_dt=min_dt,
            max_dt=max_dt,
            daily_records=daily_records,
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
        old_access_report = "Отчет по проходам" in text and "Ф.И.О" in text and "Событие" in text
        detailed_access_report = "Подробный отч" in text and "Сотрудник" in text and "Направление" in text
        return old_access_report or detailed_access_report

    @staticmethod
    def _looks_like_employee_summary_report(text: str) -> bool:
        has_daily_columns = all(
            column in text
            for column in ("Сотрудник", "Дата", "Начало дня", "Конец дня")
        )
        return has_daily_columns and (
            "О сотруднике" in text
            or "Отчет о нарушениях" in text
        )

    @staticmethod
    def _find_access_report_header_row(rows: List[List[str]]) -> int | None:
        for index, row in enumerate(rows):
            if not row:
                continue
            values = [cell.strip() for cell in row]
            if "Ф.И.О" in values and "Событие" in values:
                return index
            if "Сотрудник" in values and "Дата и время" in values and "Направление" in values:
                return index
        return None

    @staticmethod
    def _parse_access_report_row(headers: List[str], row: List[str]) -> Tuple[str, str, str, str] | None:
        values = [header.strip() for header in headers]
        if "Ф.И.О" in values and "Событие" in values:
            if len(row) < 8:
                return None
            if row[6].strip() != "Проход":
                return None
            zone_value = row[7].strip()
            direction = "entry" if zone_value == "Здание" else "exit" if zone_value == "Внешний мир" else "other"
            return row[0].strip(), row[3].strip(), row[4].strip(), direction

        data = {
            header: (row[index].strip() if index < len(row) else "")
            for index, header in enumerate(values)
            if header
        }
        employee_name = data.get("Сотрудник", "")
        dt_value = data.get("Дата и время", "")
        direction_value = data.get("Направление", "").lower()
        if not employee_name or not dt_value:
            return None
        direction = "entry" if direction_value == "вход" else "exit" if direction_value == "выход" else "other"
        return employee_name, data.get("Подразделение", ""), dt_value, direction

    @staticmethod
    def _find_employee_summary_header_row(rows: List[List[str]]) -> int | None:
        required = {"Сотрудник", "Дата", "Начало дня", "Конец дня"}
        for index, row in enumerate(rows):
            if not row:
                continue
            values = {cell.strip() for cell in row if cell.strip()}
            if required.issubset(values):
                return index
        return None

    def _parse_employee_summary_row(self, headers: List[str], row: List[str]) -> Dict[str, object] | None:
        data = {
            str(headers[index]).strip(): (row[index].strip() if index < len(row) else "")
            for index in range(len(headers))
            if str(headers[index]).strip()
        }

        employee_name = str(data.get("Сотрудник", "")).strip()
        event_date_raw = str(data.get("Дата", "")).strip()
        if not employee_name or not event_date_raw:
            return None

        event_dt = self._parse_event_date(event_date_raw)
        if event_dt is None:
            raise ValueError("не удалось распознать дату")
        employee_directory = self._resolve_directory_record(employee_name)
        if not self._should_track_employee(employee_directory):
            return None

        planned_start = self._resolve_planned_start(employee_directory, event_dt.date()) or ""
        planned_end = self._resolve_planned_end(employee_directory, event_dt.date()) or ""
        planned_minutes = self._resolve_planned_minutes(employee_directory, event_dt.date())
        scheduled_lunch_minutes = self.google_schedule_service.resolve_lunch_minutes(
            schedule_id=employee_directory.get("schedule_id", ""),
            schedule_name=employee_directory.get("schedule_name", ""),
            fallback=0,
        )

        building_minutes = self._parse_duration_minutes(str(data.get("Находился в здании", "")).strip())
        late_minutes = max(self._parse_duration_minutes(str(data.get("Опоздал", "")).strip()), 0)
        evening_overtime_minutes = max(self._parse_duration_minutes(str(data.get("Вечерняя переработка", "")).strip()), 0)
        early_leave_minutes = max(self._parse_duration_minutes(str(data.get("Ранних уходов", "")).strip()), 0)
        absence_minutes = max(self._parse_duration_minutes(str(data.get("Прогулял", "")).strip()), 0)
        morning_overtime_minutes = max(self._parse_duration_minutes(str(data.get("Утренняя переработка", "")).strip()), 0)
        balance_minutes_raw = self._parse_duration_minutes(str(data.get("Фактическая переработка", "")).strip())

        raw_first_entry = str(data.get("Начало дня", "")).strip()
        raw_last_exit = str(data.get("Конец дня", "")).strip()
        first_entry_time = self._extract_clock_value(raw_first_entry)
        last_exit_time = self._extract_clock_value(raw_last_exit)
        raw_first_lower = raw_first_entry.lower()
        raw_last_lower = raw_last_exit.lower()
        missing_entry_sentinel = "нет вход" in raw_first_lower or raw_first_entry in {"0:00", "00:00"}
        missing_exit_sentinel = (
            "нет выхода" in raw_last_lower
            or raw_last_exit in {"23:59", "23.59"}
            or raw_last_exit.endswith("(23:59)")
            or raw_last_exit.endswith("(23.59)")
        )
        if missing_entry_sentinel:
            first_entry_time = ""
        if missing_exit_sentinel:
            last_exit_time = ""
        actual_start = first_entry_time or self._shift_hhmm(planned_start, late_minutes) if late_minutes > 0 else ""
        inferred_lunch_minutes = 0
        if scheduled_lunch_minutes > 0 and first_entry_time and last_exit_time:
            start_dt = self._combine_date_and_time(event_dt.date(), first_entry_time)
            end_dt = self._combine_date_and_time(event_dt.date(), last_exit_time)
            if start_dt is not None and end_dt is not None and end_dt > start_dt:
                synthetic_intervals = [
                    {
                        "start": start_dt.isoformat(),
                        "end": end_dt.isoformat(),
                        "minutes": int((end_dt - start_dt).total_seconds() // 60),
                    }
                ]
                inferred_lunch_minutes = self._resolve_lunch_deduction(
                    employee_directory,
                    event_dt.date(),
                    synthetic_intervals,
                    building_minutes,
                )

        if balance_minutes_raw or planned_minutes:
            worked_minutes = max(planned_minutes + balance_minutes_raw, 0)
        else:
            worked_minutes = max(building_minutes, 0)
        lunch_minutes = max(building_minutes - worked_minutes, 0)
        balance_minutes = worked_minutes - planned_minutes if planned_minutes else balance_minutes_raw
        if lunch_minutes <= 0 and inferred_lunch_minutes > 0:
            lunch_minutes = inferred_lunch_minutes
            if balance_minutes_raw == 0 and building_minutes > 0 and worked_minutes == building_minutes:
                worked_minutes = max(building_minutes - lunch_minutes, 0)
                balance_minutes = worked_minutes - planned_minutes if planned_minutes else balance_minutes_raw
        if missing_exit_sentinel:
            worked_minutes = 0
            lunch_minutes = 0
            balance_minutes = -planned_minutes if planned_minutes else 0

        arrival_status = ""
        arrival_delta = 0
        if late_minutes > 0:
            arrival_status = "late"
            arrival_delta = late_minutes
        elif morning_overtime_minutes > 0:
            arrival_status = "early"
            arrival_delta = -morning_overtime_minutes
        elif first_entry_time and planned_start:
            inferred_arrival_dt = self._combine_date_and_time(event_dt.date(), first_entry_time)
            if inferred_arrival_dt is not None:
                arrival_status, arrival_delta = self._classify_arrival(
                    arrival_dt=inferred_arrival_dt,
                    planned_start=planned_start,
                    grace_minutes=self._resolve_late_after_minutes(employee_directory),
                )
        elif first_entry_time:
            arrival_status = "on_time"
            arrival_delta = 0

        departure_status = ""
        departure_delta = 0
        if early_leave_minutes > 0:
            departure_status = "early"
            departure_delta = -early_leave_minutes
        elif evening_overtime_minutes > 0:
            departure_status = "late"
            departure_delta = evening_overtime_minutes
        elif last_exit_time and planned_end:
            inferred_departure_dt = self._combine_date_and_time(event_dt.date(), last_exit_time)
            if inferred_departure_dt is not None:
                departure_status, departure_delta = self._classify_departure(
                    departure_dt=inferred_departure_dt,
                    planned_end=planned_end,
                )
        elif last_exit_time:
            departure_status = "on_time"
            departure_delta = 0
        if missing_exit_sentinel:
            departure_status = ""
            departure_delta = 0

        absence_reason = " ".join(
            value
            for value in (
                str(data.get("Причины не выхода", "")).strip(),
                str(data.get("Комм. причины отсутствия", "")).strip(),
            )
            if value
        ).strip()
        if missing_exit_sentinel and not absence_reason:
            absence_reason = "Нет отметки выхода до 23:59"
        absence_case = absence_minutes > 0 or bool(absence_reason) or missing_exit_sentinel

        return {
            "record_key": self._build_record_key(employee_directory, employee_name, event_dt.date().isoformat()),
            "employee_name": employee_name,
            "department_name": employee_directory.get("department_name", "") or str(data.get("Подразделение", "")).strip() or "Не указано",
            "event_date": event_dt.date().isoformat(),
            "employee_user_id": employee_directory.get("employee_user_id", ""),
            "manager_user_id": employee_directory.get("manager_user_id", ""),
            "manager_name": employee_directory.get("manager_name", ""),
            "schedule_name": employee_directory.get("schedule_name", ""),
            "schedule_id": employee_directory.get("schedule_id", ""),
            "planned_start": planned_start,
            "planned_end": planned_end,
            "events": [],
            "first_entry_dt": self._combine_date_and_time(event_dt.date(), first_entry_time).isoformat() if first_entry_time else "",
            "last_exit_dt": self._combine_date_and_time(event_dt.date(), last_exit_time).isoformat() if last_exit_time else "",
            "presence_intervals": [],
            "worked_minutes": worked_minutes,
            "planned_minutes": planned_minutes,
            "lunch_minutes": lunch_minutes,
            "balance_minutes": balance_minutes,
            "arrival_status_override": arrival_status,
            "arrival_delta_override": arrival_delta,
            "departure_status_override": departure_status,
            "departure_delta_override": departure_delta,
            "absence_case": absence_case,
            "employee_reason": absence_reason,
            "actual_start_override": actual_start,
            "total_passes": 0,
            "source": "skud_employee_summary",
        }

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

    def _resolve_planned_minutes(self, employee_directory: Dict[str, str], event_date: date) -> int:
        schedule_id = employee_directory.get("schedule_id", "")
        schedule_name = employee_directory.get("schedule_name", "")
        planned_minutes = self.google_schedule_service.resolve_planned_minutes(
            schedule_id=schedule_id,
            schedule_name=schedule_name,
            event_date=event_date,
            fallback=0,
        )
        if planned_minutes > 0:
            return planned_minutes

        normative_minutes = GoogleSheetsScheduleService._normative_minutes_from_schedule_name(schedule_name)
        if normative_minutes > 0:
            return normative_minutes

        planned_start = self._resolve_planned_start(employee_directory, event_date) or ""
        planned_end = self._resolve_planned_end(employee_directory, event_date) or ""
        if not planned_start or not planned_end:
            return 0
        try:
            start_dt = datetime.strptime(planned_start, "%H:%M")
            end_dt = datetime.strptime(planned_end, "%H:%M")
        except ValueError:
            return 0
        total = int((end_dt - start_dt).total_seconds() // 60)
        if total <= 0:
            return 0
        lunch_minutes = self.google_schedule_service.resolve_lunch_minutes(
            schedule_id=schedule_id,
            schedule_name=schedule_name,
            fallback=0,
        )
        if lunch_minutes > 0:
            total = max(total - lunch_minutes, 0)
        return total

    @staticmethod
    def _should_track_employee(employee_directory: Dict[str, str]) -> bool:
        role = str(employee_directory.get("role", "") or "").strip()
        return role != "top_manager"

    def _match_existing_late_notice(
        self,
        *,
        employee_user_id: str,
        event_date: str,
        planned_start: str,
        actual_start: str,
        delay_minutes: int,
    ) -> int | None:
        finder = getattr(self.case_repository, "find_matching_late_notice", None)
        updater = getattr(self.case_repository, "update_skud_match", None)
        if not callable(finder) or not callable(updater):
            return None
        matched = finder(
            employee_user_id=employee_user_id,
            event_date=event_date,
            actual_start=actual_start,
        )
        if matched is None:
            return None
        updated = updater(
            int(getattr(matched, "id", 0) or 0),
            planned_start=planned_start,
            actual_start=actual_start,
            delay_minutes=delay_minutes,
        )
        if updated is None:
            return None
        return int(getattr(updated, "id", 0) or 0)

    def _resolve_lunch_deduction(
        self,
        employee_directory: Dict[str, str],
        event_date: date,
        presence_intervals: List[Dict[str, object]],
        presence_minutes: int,
    ) -> int:
        if not presence_intervals or presence_minutes <= 0:
            return 0
        schedule_id = employee_directory.get("schedule_id", "")
        schedule_name = employee_directory.get("schedule_name", "")
        lunch_mode = self.google_schedule_service.resolve_lunch_mode(
            schedule_id=schedule_id,
            schedule_name=schedule_name,
            fallback="deduct",
        )
        if lunch_mode == "none":
            return 0

        lunch_minutes = self.google_schedule_service.resolve_lunch_minutes(
            schedule_id=schedule_id,
            schedule_name=schedule_name,
            fallback=0,
        )
        if lunch_mode == "fixed":
            lunch_start, lunch_end = self.google_schedule_service.resolve_lunch_window(
                schedule_id=schedule_id,
                schedule_name=schedule_name,
            )
            if not lunch_start or not lunch_end:
                return min(lunch_minutes, presence_minutes)
            lunch_start_dt = self._combine_date_and_time(event_date, lunch_start)
            lunch_end_dt = self._combine_date_and_time(event_date, lunch_end)
            if lunch_start_dt is None or lunch_end_dt is None or lunch_end_dt <= lunch_start_dt:
                return min(lunch_minutes, presence_minutes)
            overlap = 0
            for interval in presence_intervals:
                start_dt = self._parse_iso_datetime(str(interval.get("start", "")))
                end_dt = self._parse_iso_datetime(str(interval.get("end", "")))
                if start_dt is None or end_dt is None:
                    continue
                overlap += self._overlap_minutes(start_dt, end_dt, lunch_start_dt, lunch_end_dt)
            return min(overlap, presence_minutes)

        return min(lunch_minutes, presence_minutes)

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
        match = re.fullmatch(r"\s*(\d{2}\.\d{2}\.\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})\s*", value)
        if match:
            normalized = f"{match.group(1)} {int(match.group(2)):02d}:{match.group(3)}:{match.group(4)}"
            return datetime.strptime(normalized, "%d.%m.%Y %H:%M:%S")
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
    def _combine_date_and_time(event_date: date, hhmm: str) -> datetime | None:
        try:
            parsed = datetime.strptime(hhmm, "%H:%M").time()
        except ValueError:
            return None
        return datetime.combine(event_date, parsed)

    def _build_presence_intervals(
        self,
        *,
        raw_events: List[Dict[str, object]],
        event_date: date,
        planned_end: str,
    ) -> List[Dict[str, object]]:
        events = sorted(
            (
                {
                    "dt": self._parse_iso_datetime(str(item.get("dt", ""))),
                    "kind": str(item.get("kind", "")),
                }
                for item in raw_events
            ),
            key=lambda item: item["dt"] or datetime.min,
        )
        intervals: List[Dict[str, object]] = []
        open_entry: datetime | None = None
        for event in events:
            dt_value = event["dt"]
            if dt_value is None:
                continue
            kind = event["kind"]
            if kind == "entry":
                if open_entry is None:
                    open_entry = dt_value
                continue
            if kind == "exit" and open_entry is not None and dt_value > open_entry:
                minutes = int((dt_value - open_entry).total_seconds() // 60)
                intervals.append(
                    {
                        "start": open_entry.isoformat(),
                        "end": dt_value.isoformat(),
                        "minutes": max(minutes, 0),
                    }
                )
                open_entry = None

        if open_entry is not None:
            planned_end_dt = self._combine_date_and_time(event_date, planned_end)
            if planned_end_dt is not None and planned_end_dt > open_entry:
                minutes = int((planned_end_dt - open_entry).total_seconds() // 60)
                intervals.append(
                    {
                        "start": open_entry.isoformat(),
                        "end": planned_end_dt.isoformat(),
                        "minutes": max(minutes, 0),
                    }
                )
        return intervals

    def _finalize_daily_records(
        self,
        *,
        filename: str,
        created_by_user_id: str,
        create_cases: bool,
        total_rows: int,
        errors: List[str],
        min_dt: datetime | None,
        max_dt: datetime | None,
        daily_records: Dict[Tuple[str, str], Dict[str, object]],
    ) -> SkudImportResult:
        created_cases = 0
        samples: List[str] = []
        attendance_rows: List[Dict[str, object]] = []
        arrivals_early = 0
        arrivals_on_time = 0
        arrivals_late = 0
        departures_early = 0
        departures_on_time = 0
        departures_late = 0

        self._inject_approved_substitution_days(
            daily_records=daily_records,
            period_start=min_dt.date() if min_dt else None,
            period_end=max_dt.date() if max_dt else None,
        )

        for item in daily_records.values():
            planned_start = str(item.get("planned_start", "")).strip()
            planned_end = str(item.get("planned_end", "")).strip()
            event_date_str = str(item.get("event_date", "")).strip()
            event_date = self._parse_event_date(event_date_str)
            if event_date is None:
                continue

            arrival_dt = self._parse_iso_datetime(str(item.get("first_entry_dt", "")).strip())
            departure_dt = self._parse_iso_datetime(str(item.get("last_exit_dt", "")).strip())
            raw_events = list(item.get("events", []) or [])
            presence_intervals = list(item.get("presence_intervals", []) or [])
            if not presence_intervals:
                presence_intervals = self._build_presence_intervals(
                    raw_events=raw_events,
                    event_date=event_date.date(),
                    planned_end=planned_end,
                )

            presence_minutes = sum(int(interval.get("minutes", 0) or 0) for interval in presence_intervals)
            planned_minutes = int(item.get("planned_minutes", self._resolve_planned_minutes(item, event_date.date())) or 0)
            lunch_minutes = int(item.get("lunch_minutes", 0) or 0)
            worked_minutes = int(item.get("worked_minutes", 0) or 0)
            balance_minutes = int(item.get("balance_minutes", 0) or 0)
            if not item.get("worked_minutes") and not item.get("lunch_minutes") and not item.get("balance_minutes"):
                lunch_minutes = self._resolve_lunch_deduction(item, event_date.date(), presence_intervals, presence_minutes)
                worked_minutes = max(presence_minutes - lunch_minutes, 0)
                balance_minutes = worked_minutes - planned_minutes
            if lunch_minutes <= 0 and arrival_dt and departure_dt and departure_dt > arrival_dt:
                inferred_display_lunch = self._resolve_lunch_deduction(
                    item,
                    event_date.date(),
                    [
                        {
                            "start": arrival_dt.isoformat(),
                            "end": departure_dt.isoformat(),
                            "minutes": int((departure_dt - arrival_dt).total_seconds() // 60),
                        }
                    ],
                    int((departure_dt - arrival_dt).total_seconds() // 60),
                )
                if inferred_display_lunch > 0:
                    lunch_minutes = inferred_display_lunch

            arrival_status = str(item.get("arrival_status_override", "")).strip()
            arrival_delta = int(item.get("arrival_delta_override", 0) or 0)
            if not arrival_status and arrival_dt and planned_start:
                arrival_status, arrival_delta = self._classify_arrival(
                    arrival_dt=arrival_dt,
                    planned_start=planned_start,
                    grace_minutes=self._resolve_late_after_minutes(item),
                )

            if arrival_status == "early":
                arrivals_early += 1
            elif arrival_status == "on_time":
                arrivals_on_time += 1
            elif arrival_status == "late":
                arrivals_late += 1
                if len(samples) < 5:
                    samples.append(
                        "{name} | {date} | {time} | +{delay} мин".format(
                            name=item["employee_name"],
                            date=event_date_str,
                            time=(arrival_dt.strftime("%H:%M") if arrival_dt else str(item.get("actual_start_override", "") or "-")),
                            delay=arrival_delta,
                        )
                    )

            departure_status = str(item.get("departure_status_override", "")).strip()
            departure_delta = int(item.get("departure_delta_override", 0) or 0)
            if not departure_status and departure_dt and planned_end:
                departure_status, departure_delta = self._classify_departure(
                    departure_dt=departure_dt,
                    planned_end=planned_end,
                )

            if departure_status == "early":
                departures_early += 1
            elif departure_status == "on_time":
                departures_on_time += 1
            elif departure_status == "late":
                departures_late += 1

            if create_cases and bool(item.get("absence_case")):
                employee_reason = str(item.get("employee_reason", "")).strip()
                status = (
                    AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value
                    if employee_reason
                    else AttendanceCaseStatus.AWAITING_EMPLOYEE_REASON.value
                )
                self.case_repository.create_case(
                    employee_user_id=str(item.get("employee_user_id", "")),
                    employee_name=str(item["employee_name"]),
                    department_name=str(item["department_name"]),
                    manager_user_id=str(item.get("manager_user_id", "")),
                    manager_name=str(item.get("manager_name", "")),
                    case_type=AttendanceCaseType.ABSENT.value,
                    status=status,
                    event_date=event_date_str,
                    planned_start=planned_start,
                    actual_start="-",
                    delay_minutes=0,
                    employee_reason=employee_reason,
                    source=str(item.get("source", "skud_report") or "skud_report"),
                )
                created_cases += 1
            elif create_cases and arrival_status == "late":
                actual_start = str(item.get("actual_start_override", "")).strip() or (arrival_dt.strftime("%H:%M") if arrival_dt else "")
                matched_case_id = self._match_existing_late_notice(
                    employee_user_id=str(item.get("employee_user_id", "")),
                    event_date=event_date_str,
                    planned_start=planned_start,
                    actual_start=actual_start,
                    delay_minutes=arrival_delta,
                )
                if matched_case_id is None:
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
                        actual_start=actual_start or "-",
                        delay_minutes=arrival_delta,
                        employee_reason="",
                        source=str(item.get("source", "skud_report") or "skud_report"),
                    )
                    created_cases += 1

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
                    "raw_events_json": json.dumps(raw_events, ensure_ascii=False),
                    "presence_intervals_json": json.dumps(presence_intervals, ensure_ascii=False),
                    "first_entry_time": arrival_dt.strftime("%H:%M") if arrival_dt else "",
                    "arrival_status": arrival_status,
                    "arrival_delta_minutes": arrival_delta,
                    "last_exit_time": departure_dt.strftime("%H:%M") if departure_dt else "",
                    "departure_status": departure_status,
                    "departure_delta_minutes": departure_delta,
                    "worked_minutes": worked_minutes,
                    "planned_minutes": planned_minutes,
                    "lunch_minutes": lunch_minutes,
                    "balance_minutes": balance_minutes,
                    "late_compensated": False,
                    "total_passes": int(item.get("total_passes", 0) or 0),
                    "source": str(item.get("source", "skud_report") or "skud_report"),
                }
            )

        self._apply_weekly_late_compensation(attendance_rows)
        self.day_record_repository.upsert_many(attendance_rows)

        import_id = 0
        if create_cases:
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

    @staticmethod
    def _overlap_minutes(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> int:
        start = max(start_a, start_b)
        end = min(end_a, end_b)
        if end <= start:
            return 0
        return int((end - start).total_seconds() // 60)

    @staticmethod
    def _iso_week_key(event_date_str: str) -> tuple[int, int] | tuple[None, None]:
        try:
            event_date = date.fromisoformat(event_date_str)
        except ValueError:
            return (None, None)
        iso = event_date.isocalendar()
        return iso.year, iso.week

    def _apply_weekly_late_compensation(self, attendance_rows: List[Dict[str, object]]) -> None:
        weekly_totals: Dict[Tuple[str, int | None, int | None], Dict[str, int]] = {}
        for row in attendance_rows:
            employee_key = str(row.get("employee_user_id", "") or row.get("employee_name", "")).strip()
            week_key = self._iso_week_key(str(row.get("event_date", "")))
            key = (employee_key, week_key[0], week_key[1])
            stats = weekly_totals.setdefault(key, {"balance": 0, "late": 0, "overwork": 0})
            balance_value = int(row.get("balance_minutes", 0) or 0)
            stats["balance"] += balance_value
            if self._attendance_row_day_type(row) == "Обычный" and balance_value > 0:
                stats["overwork"] += balance_value
            if str(row.get("arrival_status", "")) == "late":
                stats["late"] += int(row.get("arrival_delta_minutes", 0) or 0)

        for row in attendance_rows:
            if str(row.get("arrival_status", "")) != "late" or self._attendance_row_day_type(row) != "Обычный":
                row["late_compensated"] = False
                continue
            employee_key = str(row.get("employee_user_id", "") or row.get("employee_name", "")).strip()
            week_key = self._iso_week_key(str(row.get("event_date", "")))
            stats = weekly_totals.get((employee_key, week_key[0], week_key[1]), {"balance": 0, "late": 0, "overwork": 0})
            row["late_compensated"] = stats["late"] > 0 and stats["overwork"] >= stats["late"]

    @staticmethod
    def _attendance_row_day_type(row: Dict[str, object]) -> str:
        source = str(row.get("source", "") or "").strip()
        if source == "approved_substitution":
            return "Замещение"
        first_entry = str(row.get("first_entry_time", "") or "").strip()
        last_exit = str(row.get("last_exit_time", "") or "").strip()
        total_passes = int(row.get("total_passes", 0) or 0)
        if first_entry and not last_exit:
            return "Нет выхода"
        if last_exit and not first_entry:
            return "Нет входа"
        if not first_entry and not last_exit and total_passes <= 0:
            return "Нет проходов"
        return "Обычный"

    @staticmethod
    def _classify_arrival(*, arrival_dt: datetime, planned_start: str, grace_minutes: int) -> tuple[str, int]:
        planned_time = SkudImportService._parse_time(planned_start)
        planned_dt = datetime.combine(arrival_dt.date(), planned_time)
        delta_minutes = int((arrival_dt - planned_dt).total_seconds() // 60)
        if delta_minutes < 0:
            return "early", delta_minutes
        if delta_minutes == 0:
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
    def _parse_duration_minutes(value: str) -> int:
        normalized = (value or "").strip()
        if not normalized:
            return 0
        if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", normalized):
            return int(round(float(normalized) * 24 * 60))
        match = re.fullmatch(r"([+-]?)(\d{1,2}):(\d{2})", normalized)
        if match:
            sign = -1 if match.group(1) == "-" else 1
            return sign * (int(match.group(2)) * 60 + int(match.group(3)))
        return 0

    @staticmethod
    def _extract_clock_value(value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            return ""
        lower = normalized.lower()
        if "нет вход" in lower or "нет выхода" in lower:
            return ""
        if re.fullmatch(r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", normalized):
            numeric_value = float(normalized)
            if 0 <= numeric_value < 1:
                total_minutes = int(round(numeric_value * 24 * 60)) % (24 * 60)
                return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"
        match = re.search(r"(\d{1,2}:\d{2})", normalized)
        if not match:
            return ""
        hour_text, minute_text = match.group(1).split(":", 1)
        return f"{int(hour_text):02d}:{minute_text}"

    @staticmethod
    def _shift_hhmm(value: str, delta_minutes: int) -> str:
        if not value:
            return ""
        try:
            parsed = datetime.strptime(value, "%H:%M")
        except ValueError:
            return ""
        return (parsed + timedelta(minutes=delta_minutes)).strftime("%H:%M")

    @staticmethod
    def _build_record_key(employee_directory: Dict[str, str], employee_name: str, event_date: str) -> str:
        employee_user_id = employee_directory.get("employee_user_id", "")
        if employee_user_id:
            return f"user:{employee_user_id}:{event_date}"
        return f"name:{employee_name}:{event_date}"

    def _inject_approved_substitution_days(
        self,
        *,
        daily_records: Dict[Tuple[str, str], Dict[str, object]],
        period_start: date | None,
        period_end: date | None,
    ) -> None:
        if period_start is None or period_end is None or period_end < period_start:
            return

        approved = self.substitution_repository.list_approved_overlapping(
            period_start.isoformat(),
            period_end.isoformat(),
        )
        for draft in approved:
            employee_name = str(getattr(draft, "target_manager", "") or "").strip()
            target_user_id = str(getattr(draft, "target_user_id", "") or "").strip() or str(
                getattr(draft, "created_by_user_id", "") or ""
            ).strip()
            if not employee_name:
                continue

            start = self._parse_event_date(str(getattr(draft, "date_from", "") or ""))
            end = self._parse_event_date(str(getattr(draft, "date_to", "") or ""))
            if start is None or end is None:
                continue

            current_date = max(start.date(), period_start)
            final_date = min(end.date(), period_end)
            while current_date <= final_date:
                key = (employee_name, current_date.isoformat())
                if key in daily_records:
                    current_date += timedelta(days=1)
                    continue

                employee_directory = self._resolve_directory_record(employee_name)
                if target_user_id and not employee_directory.get("employee_user_id"):
                    employee_directory["employee_user_id"] = target_user_id
                if not self._should_track_employee(employee_directory):
                    current_date += timedelta(days=1)
                    continue
                planned_start = self._resolve_planned_start(employee_directory, current_date) or ""
                planned_end = self._resolve_planned_end(employee_directory, current_date) or ""
                daily_records[key] = {
                    "record_key": self._build_record_key(employee_directory, employee_name, current_date.isoformat()),
                    "employee_name": employee_name,
                    "department_name": employee_directory.get("department_name", "") or "Не указано",
                    "event_date": current_date.isoformat(),
                    "employee_user_id": employee_directory.get("employee_user_id", ""),
                    "manager_user_id": employee_directory.get("manager_user_id", ""),
                    "manager_name": employee_directory.get("manager_name", ""),
                    "schedule_name": employee_directory.get("schedule_name", ""),
                    "schedule_id": employee_directory.get("schedule_id", ""),
                    "planned_start": planned_start,
                    "planned_end": planned_end,
                    "events": [],
                    "first_entry_dt": "",
                    "last_exit_dt": "",
                    "total_passes": 0,
                    "source": "approved_substitution",
                }
                current_date += timedelta(days=1)
