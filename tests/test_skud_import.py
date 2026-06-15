from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.skud_import import SkudImportService


class _FakeAttendanceCaseRepository:
    def __init__(self):
        self.created = []
        self.matched = None
        self.updated_matches = []

    def create_case(self, **kwargs):
        self.created.append(kwargs)
        return len(self.created)

    def find_matching_late_notice(self, *, employee_user_id: str, event_date: str, actual_start: str, max_diff_minutes: int = 120):
        return self.matched

    def update_skud_match(self, case_id: int, *, planned_start: str, actual_start: str, delay_minutes: int):
        row = SimpleNamespace(id=case_id, planned_start=planned_start, actual_start=actual_start, delay_minutes=delay_minutes)
        self.updated_matches.append(row)
        return row


class _FakeApprovalRepository:
    def __init__(self):
        self.created = []

    def create_if_missing(self, **kwargs):
        self.created.append(kwargs)
        return len(self.created)


class _FakeEmployeeDirectoryRepository:
    def get_by_employee_name(self, employee_name: str):
        return None


class _FakeSkudImportRepository:
    def __init__(self):
        self.created = []

    def create(self, **kwargs):
        self.created.append(kwargs)
        return 42


class _FakeAttendanceDayRecordRepository:
    def __init__(self):
        self.rows = []

    def upsert_many(self, rows):
        self.rows.extend(rows)
        return len(rows)


class _FakeGoogleSheetsDirectoryService:
    def get_by_employee_name(self, employee_name: str):
        return None


class _FakeGoogleSheetsScheduleService:
    def resolve_planned_start(self, *, schedule_id: str = "", schedule_name: str = "", event_date, fallback: str = "08:30"):
        if schedule_name == "Пятидневка - Девушки 08:30-12:30 / 14:00-17:15":
            return "08:30"
        return fallback

    def resolve_late_after_minutes(self, *, schedule_id: str = "", schedule_name: str = "", fallback: int = 10):
        if schedule_name == "Пятидневка - Девушки 08:30-12:30 / 14:00-17:15":
            return 10
        return fallback

    def resolve_planned_end(self, *, schedule_id: str = "", schedule_name: str = "", event_date, fallback: str = "18:00"):
        if schedule_name == "Пятидневка - Девушки 08:30-12:30 / 14:00-17:15":
            return "17:15"
        return fallback

    def resolve_planned_minutes(self, *, schedule_id: str = "", schedule_name: str = "", event_date, fallback: int = 0):
        if schedule_name == "Пятидневка - Девушки 08:30-12:30 / 14:00-17:15":
            return 429
        return fallback

    def resolve_lunch_minutes(self, *, schedule_id: str = "", schedule_name: str = "", fallback: int = 0):
        if schedule_name == "Пятидневка - Девушки 08:30-12:30 / 14:00-17:15":
            return 90
        return fallback

    def resolve_lunch_window(self, *, schedule_id: str = "", schedule_name: str = ""):
        if schedule_name == "Пятидневка - Девушки 08:30-12:30 / 14:00-17:15":
            return ("12:30", "14:00")
        return ("", "")

    def resolve_lunch_mode(self, *, schedule_id: str = "", schedule_name: str = "", fallback: str = "deduct"):
        if schedule_name == "Пятидневка - Девушки 08:30-12:30 / 14:00-17:15":
            return "fixed"
        return fallback


class _FallbackScheduleService:
    def resolve_planned_start(self, *, schedule_id: str = "", schedule_name: str = "", event_date, fallback: str = "08:30"):
        return "08:30"

    def resolve_late_after_minutes(self, *, schedule_id: str = "", schedule_name: str = "", fallback: int = 10):
        return 10

    def resolve_planned_end(self, *, schedule_id: str = "", schedule_name: str = "", event_date, fallback: str = "18:00"):
        return "17:15"

    def resolve_planned_minutes(self, *, schedule_id: str = "", schedule_name: str = "", event_date, fallback: int = 0):
        return 0

    def resolve_lunch_minutes(self, *, schedule_id: str = "", schedule_name: str = "", fallback: int = 0):
        return 90

    def resolve_lunch_window(self, *, schedule_id: str = "", schedule_name: str = ""):
        return ("12:30", "14:00")

    def resolve_lunch_mode(self, *, schedule_id: str = "", schedule_name: str = "", fallback: str = "deduct"):
        return "fixed"


class _FakeSubstitutionRepository:
    def __init__(self, drafts=None):
        self.drafts = list(drafts or [])

    def list_approved_overlapping(self, date_from: str, date_to: str):
        return list(self.drafts)


class SkudImportServiceTests(unittest.TestCase):
    def test_generic_csv_import_creates_history_without_name_error(self) -> None:
        csv_payload = (
            "employee_name;case_type;planned_start;event_date;actual_start;delay_minutes;department_name\n"
            "Иванов Иван Иванович;late;08:30;2026-05-04;08:44;14;Отдел продаж\n"
        ).encode("utf-8")

        with patch("app.services.skud_import.AttendanceCaseRepository", _FakeAttendanceCaseRepository), patch(
            "app.services.skud_import.ApprovalRepository", _FakeApprovalRepository
        ), patch(
            "app.services.skud_import.EmployeeDirectoryRepository", _FakeEmployeeDirectoryRepository
        ), patch(
            "app.services.skud_import.SkudImportRepository", _FakeSkudImportRepository
        ), patch(
            "app.services.skud_import.AttendanceDayRecordRepository", _FakeAttendanceDayRecordRepository
        ), patch(
            "app.services.skud_import.GoogleSheetsDirectoryService.from_settings",
            return_value=_FakeGoogleSheetsDirectoryService(),
        ), patch(
            "app.services.skud_import.SubstitutionRepository",
            return_value=_FakeSubstitutionRepository(),
        ):
            service = SkudImportService()
            result = service.import_csv(filename="report.csv", content=csv_payload, created_by_user_id="sec_001")

        self.assertEqual(result.total_rows, 1)
        self.assertEqual(result.created_cases, 1)
        self.assertEqual(result.error_rows, 0)
        self.assertEqual(result.period_start, "2026-05-04")
        self.assertEqual(result.period_end, "2026-05-04")

    def test_access_report_import_uses_schedule_planned_start(self) -> None:
        access_report = (
            "Отчет по проходам\n"
            "Ф.И.О;Таб.№;Подразделение;Подразделение;Дата и время;Точка;Событие;Зона\n"
            "Иванова Анна Сергеевна;;;Отдел продаж;04.05.2026 08:44:00;Вход;Проход;Здание\n"
        ).encode("utf-8")

        with patch("app.services.skud_import.AttendanceCaseRepository", _FakeAttendanceCaseRepository), patch(
            "app.services.skud_import.ApprovalRepository", _FakeApprovalRepository
        ), patch(
            "app.services.skud_import.EmployeeDirectoryRepository", _FakeEmployeeDirectoryRepository
        ), patch(
            "app.services.skud_import.SkudImportRepository", _FakeSkudImportRepository
        ), patch(
            "app.services.skud_import.AttendanceDayRecordRepository", _FakeAttendanceDayRecordRepository
        ), patch(
            "app.services.skud_import.GoogleSheetsDirectoryService.from_settings",
            return_value=SimpleNamespace(
                get_by_employee_name=lambda employee_name: SimpleNamespace(
                    employee_name=employee_name,
                    employee_user_id="max_010",
                    manager_name="Петров Петр Сергеевич",
                    manager_user_id="max_020",
                    department_name="Отдел продаж",
                    schedule_name="Пятидневка - Девушки 08:30-12:30 / 14:00-17:15",
                    schedule_id="ГР003",
                    role="employee",
                    is_active=True,
                )
            ),
        ), patch(
            "app.services.skud_import.GoogleSheetsScheduleService.from_settings",
            return_value=_FakeGoogleSheetsScheduleService(),
        ), patch(
            "app.services.skud_import.SubstitutionRepository",
            return_value=_FakeSubstitutionRepository(),
        ):
            service = SkudImportService()
            result = service.import_csv(filename="report.txt", content=access_report, created_by_user_id="sec_001")

        self.assertEqual(result.created_cases, 1)
        created_case = service.case_repository.created[0]
        self.assertEqual(created_case["planned_start"], "08:30")
        self.assertEqual(created_case["delay_minutes"], 14)
        self.assertEqual(result.period_start, "2026-05-04")
        self.assertEqual(result.period_end, "2026-05-04")

    def test_access_report_marks_one_minute_delay_as_late(self) -> None:
        access_report = (
            "Отчет по проходам\n"
            "Ф.И.О;Таб.№;Подразделение;Подразделение;Дата и время;Точка;Событие;Зона\n"
            "Иванова Анна Сергеевна;;;Отдел продаж;04.05.2026 08:31:00;Вход;Проход;Здание\n"
        ).encode("utf-8")

        day_repo = _FakeAttendanceDayRecordRepository()

        with patch("app.services.skud_import.AttendanceCaseRepository", _FakeAttendanceCaseRepository), patch(
            "app.services.skud_import.ApprovalRepository", _FakeApprovalRepository
        ), patch(
            "app.services.skud_import.EmployeeDirectoryRepository", _FakeEmployeeDirectoryRepository
        ), patch(
            "app.services.skud_import.SkudImportRepository", _FakeSkudImportRepository
        ), patch(
            "app.services.skud_import.AttendanceDayRecordRepository", lambda: day_repo
        ), patch(
            "app.services.skud_import.GoogleSheetsDirectoryService.from_settings",
            return_value=SimpleNamespace(
                get_by_employee_name=lambda employee_name: SimpleNamespace(
                    employee_name=employee_name,
                    employee_user_id="max_010",
                    manager_name="Петров Петр Сергеевич",
                    manager_user_id="max_020",
                    department_name="Отдел продаж",
                    schedule_name="Пятидневка - Девушки 08:30-12:30 / 14:00-17:15",
                    schedule_id="ГР003",
                    role="employee",
                    is_active=True,
                )
            ),
        ), patch(
            "app.services.skud_import.GoogleSheetsScheduleService.from_settings",
            return_value=_FakeGoogleSheetsScheduleService(),
        ), patch(
            "app.services.skud_import.SubstitutionRepository",
            return_value=_FakeSubstitutionRepository(),
        ):
            service = SkudImportService()
            result = service.import_csv(filename="report.txt", content=access_report, created_by_user_id="sec_001")

        self.assertEqual(result.arrivals_late, 1)
        self.assertEqual(result.arrivals_on_time, 0)
        self.assertEqual(len(day_repo.rows), 1)
        self.assertEqual(day_repo.rows[0]["arrival_status"], "late")
        self.assertEqual(day_repo.rows[0]["arrival_delta_minutes"], 1)

    def test_access_report_import_tracks_early_arrival_and_late_departure(self) -> None:
        access_report = (
            "Отчет по проходам\n"
            "Ф.И.О;Таб.№;Подразделение;Подразделение;Дата и время;Точка;Событие;Зона\n"
            "Иванова Анна Сергеевна;;;Отдел продаж;04.05.2026 08:20:00;Вход;Проход;Здание\n"
            "Иванова Анна Сергеевна;;;Отдел продаж;04.05.2026 17:40:00;Выход;Проход;Внешний мир\n"
        ).encode("utf-8")

        day_repo = _FakeAttendanceDayRecordRepository()

        with patch("app.services.skud_import.AttendanceCaseRepository", _FakeAttendanceCaseRepository), patch(
            "app.services.skud_import.ApprovalRepository", _FakeApprovalRepository
        ), patch(
            "app.services.skud_import.EmployeeDirectoryRepository", _FakeEmployeeDirectoryRepository
        ), patch(
            "app.services.skud_import.SkudImportRepository", _FakeSkudImportRepository
        ), patch(
            "app.services.skud_import.AttendanceDayRecordRepository", lambda: day_repo
        ), patch(
            "app.services.skud_import.GoogleSheetsDirectoryService.from_settings",
            return_value=SimpleNamespace(
                get_by_employee_name=lambda employee_name: SimpleNamespace(
                    employee_name=employee_name,
                    employee_user_id="max_010",
                    manager_name="Петров Петр Сергеевич",
                    manager_user_id="max_020",
                    department_name="Отдел продаж",
                    schedule_name="Пятидневка - Девушки 08:30-12:30 / 14:00-17:15",
                    schedule_id="ГР003",
                    role="employee",
                    is_active=True,
                )
            ),
        ), patch(
            "app.services.skud_import.GoogleSheetsScheduleService.from_settings",
            return_value=_FakeGoogleSheetsScheduleService(),
        ), patch(
            "app.services.skud_import.SubstitutionRepository",
            return_value=_FakeSubstitutionRepository(),
        ):
            service = SkudImportService()
            result = service.import_csv(filename="report.txt", content=access_report, created_by_user_id="sec_001")

        self.assertEqual(result.error_rows, 0)
        self.assertEqual(result.arrivals_early, 1)
        self.assertEqual(result.arrivals_on_time, 0)
        self.assertEqual(result.arrivals_late, 0)
        self.assertEqual(result.departures_late, 1)
        self.assertEqual(len(day_repo.rows), 1)
        record = day_repo.rows[0]
        self.assertEqual(record["arrival_status"], "early")
        self.assertEqual(record["departure_status"], "late")
        self.assertEqual(record["planned_end"], "17:15")
        self.assertEqual(record["planned_minutes"], 429)
        self.assertEqual(record["worked_minutes"], 470)
        self.assertEqual(record["lunch_minutes"], 90)
        self.assertEqual(record["balance_minutes"], 41)
        self.assertEqual(record["late_compensated"], False)

    def test_access_report_backfill_skips_case_creation_but_populates_day_records(self) -> None:
        access_report = (
            "Отчет по проходам\n"
            "Ф.И.О;Таб.№;Подразделение;Подразделение;Дата и время;Точка;Событие;Зона\n"
            "Иванова Анна Сергеевна;;;Отдел продаж;04.05.2026 08:20:00;Вход;Проход;Здание\n"
            "Иванова Анна Сергеевна;;;Отдел продаж;04.05.2026 17:40:00;Выход;Проход;Внешний мир\n"
        ).encode("utf-8")

        day_repo = _FakeAttendanceDayRecordRepository()

        with patch("app.services.skud_import.AttendanceCaseRepository", _FakeAttendanceCaseRepository), patch(
            "app.services.skud_import.ApprovalRepository", _FakeApprovalRepository
        ), patch(
            "app.services.skud_import.EmployeeDirectoryRepository", _FakeEmployeeDirectoryRepository
        ), patch(
            "app.services.skud_import.SkudImportRepository", _FakeSkudImportRepository
        ), patch(
            "app.services.skud_import.AttendanceDayRecordRepository", lambda: day_repo
        ), patch(
            "app.services.skud_import.GoogleSheetsDirectoryService.from_settings",
            return_value=SimpleNamespace(
                get_by_employee_name=lambda employee_name: SimpleNamespace(
                    employee_name=employee_name,
                    employee_user_id="max_010",
                    manager_name="Петров Петр Сергеевич",
                    manager_user_id="max_020",
                    department_name="Отдел продаж",
                    schedule_name="Пятидневка - Девушки 08:30-12:30 / 14:00-17:15",
                    schedule_id="ГР003",
                    role="employee",
                    is_active=True,
                )
            ),
        ), patch(
            "app.services.skud_import.GoogleSheetsScheduleService.from_settings",
            return_value=_FakeGoogleSheetsScheduleService(),
        ), patch(
            "app.services.skud_import.SubstitutionRepository",
            return_value=_FakeSubstitutionRepository(),
        ):
            service = SkudImportService()
            result = service.import_csv(
                filename="report.txt",
                content=access_report,
                created_by_user_id="sec_001",
                create_cases=False,
            )

        self.assertEqual(result.created_cases, 0)
        self.assertEqual(len(day_repo.rows), 1)
        record = day_repo.rows[0]
        self.assertEqual(record["arrival_status"], "early")
        self.assertEqual(record["departure_status"], "late")
        self.assertEqual(record["planned_end"], "17:15")
        self.assertEqual(record["planned_minutes"], 429)
        self.assertEqual(record["worked_minutes"], 470)

    def test_access_report_matches_existing_late_notice_without_creating_duplicate_case(self) -> None:
        access_report = (
            "Отчет по проходам\n"
            "Ф.И.О;Таб.№;Подразделение;Подразделение;Дата и время;Точка;Событие;Зона\n"
            "Иванова Анна Сергеевна;;;Отдел продаж;04.05.2026 08:44:00;Вход;Проход;Здание\n"
        ).encode("utf-8")

        case_repo = _FakeAttendanceCaseRepository()
        case_repo.matched = SimpleNamespace(id=55)

        with patch("app.services.skud_import.AttendanceCaseRepository", lambda: case_repo), patch(
            "app.services.skud_import.ApprovalRepository", _FakeApprovalRepository
        ), patch(
            "app.services.skud_import.EmployeeDirectoryRepository", _FakeEmployeeDirectoryRepository
        ), patch(
            "app.services.skud_import.SkudImportRepository", _FakeSkudImportRepository
        ), patch(
            "app.services.skud_import.AttendanceDayRecordRepository", _FakeAttendanceDayRecordRepository
        ), patch(
            "app.services.skud_import.GoogleSheetsDirectoryService.from_settings",
            return_value=SimpleNamespace(
                get_by_employee_name=lambda employee_name: SimpleNamespace(
                    employee_name=employee_name,
                    employee_user_id="max_010",
                    manager_name="Петров Петр Сергеевич",
                    manager_user_id="max_020",
                    department_name="Отдел продаж",
                    schedule_name="Пятидневка - Девушки 08:30-12:30 / 14:00-17:15",
                    schedule_id="ГР003",
                    role="employee",
                    is_active=True,
                )
            ),
        ), patch(
            "app.services.skud_import.GoogleSheetsScheduleService.from_settings",
            return_value=_FakeGoogleSheetsScheduleService(),
        ), patch(
            "app.services.skud_import.SubstitutionRepository",
            return_value=_FakeSubstitutionRepository(),
        ):
            service = SkudImportService()
            result = service.import_csv(filename="report.txt", content=access_report, created_by_user_id="sec_001")

        self.assertEqual(result.created_cases, 0)
        self.assertEqual(case_repo.created, [])
        self.assertEqual(len(case_repo.updated_matches), 1)
        self.assertEqual(case_repo.updated_matches[0].id, 55)
        self.assertEqual(case_repo.updated_matches[0].actual_start, "08:44")
        self.assertEqual(case_repo.updated_matches[0].delay_minutes, 14)

    def test_access_report_adds_substitution_day_without_passes(self) -> None:
        access_report = (
            "Отчет по проходам\n"
            "Ф.И.О;Таб.№;Подразделение;Подразделение;Дата и время;Точка;Событие;Зона\n"
            "Иванова Анна Сергеевна;;;Отдел продаж;04.05.2026 08:20:00;Вход;Проход;Здание\n"
            "Иванова Анна Сергеевна;;;Отдел продаж;04.05.2026 17:40:00;Выход;Проход;Внешний мир\n"
        ).encode("utf-8")

        day_repo = _FakeAttendanceDayRecordRepository()
        substitution_repo = _FakeSubstitutionRepository(
            drafts=[
                SimpleNamespace(
                    created_by_user_id="mgr-1",
                    target_manager="Петров Петр Сергеевич",
                    target_user_id="mgr-1",
                    replacement_user="Волков Игорь Павлович",
                    replacement_user_id="emp-2",
                    reason="Отпуск",
                    date_from="2026-05-04",
                    date_to="2026-05-04",
                    status="approved",
                )
            ]
        )

        def _directory_lookup(employee_name: str):
            if employee_name == "Иванова Анна Сергеевна":
                return SimpleNamespace(
                    employee_name=employee_name,
                    employee_user_id="max_010",
                    manager_name="Петров Петр Сергеевич",
                    manager_user_id="max_020",
                    department_name="Отдел продаж",
                    schedule_name="Пятидневка - Девушки 08:30-12:30 / 14:00-17:15",
                    schedule_id="ГР003",
                    role="employee",
                    is_active=True,
                )
            if employee_name == "Петров Петр Сергеевич":
                return SimpleNamespace(
                    employee_name=employee_name,
                    employee_user_id="mgr-1",
                    manager_name="Сидоров Сидор Сидорович",
                    manager_user_id="top-1",
                    department_name="Отдел продаж",
                    schedule_name="Пятидневка - Девушки 08:30-12:30 / 14:00-17:15",
                    schedule_id="ГР003",
                    role="manager",
                    is_active=True,
                )
            return None

        with patch("app.services.skud_import.AttendanceCaseRepository", _FakeAttendanceCaseRepository), patch(
            "app.services.skud_import.ApprovalRepository", _FakeApprovalRepository
        ), patch(
            "app.services.skud_import.EmployeeDirectoryRepository", _FakeEmployeeDirectoryRepository
        ), patch(
            "app.services.skud_import.SkudImportRepository", _FakeSkudImportRepository
        ), patch(
            "app.services.skud_import.AttendanceDayRecordRepository", lambda: day_repo
        ), patch(
            "app.services.skud_import.GoogleSheetsDirectoryService.from_settings",
            return_value=SimpleNamespace(
                get_by_employee_name=_directory_lookup,
            ),
        ), patch(
            "app.services.skud_import.GoogleSheetsScheduleService.from_settings",
            return_value=_FakeGoogleSheetsScheduleService(),
        ), patch(
            "app.services.skud_import.SubstitutionRepository",
            return_value=substitution_repo,
        ):
            service = SkudImportService()
            result = service.import_csv(filename="report.txt", content=access_report, created_by_user_id="sec_001")

        self.assertEqual(result.error_rows, 0)
        self.assertEqual(result.unique_employees, 2)
        self.assertEqual(len(day_repo.rows), 2)
        substitution_row = next(row for row in day_repo.rows if row["employee_user_id"] == "mgr-1")
        self.assertEqual(substitution_row["event_date"], "2026-05-04")
        self.assertEqual(substitution_row["total_passes"], 0)
        self.assertEqual(substitution_row["first_entry_time"], "")
        self.assertEqual(substitution_row["source"], "approved_substitution")
        self.assertEqual(substitution_row["planned_minutes"], 429)
        self.assertEqual(substitution_row["worked_minutes"], 0)
        self.assertEqual(substitution_row["balance_minutes"], -429)

    def test_access_report_tracks_manager_and_hr_roles(self) -> None:
        access_report = (
            "Отчет по проходам\n"
            "Ф.И.О;Таб.№;Подразделение;Подразделение;Дата и время;Точка;Событие;Зона\n"
            "Петров Петр Сергеевич;;;Руководство;04.05.2026 08:44:00;Вход;Проход;Здание\n"
            "Кадрова Анна Сергеевна;;;HR;04.05.2026 08:41:00;Вход;Проход;Здание\n"
        ).encode("utf-8")

        day_repo = _FakeAttendanceDayRecordRepository()

        def _directory_lookup(employee_name: str):
            if employee_name == "Петров Петр Сергеевич":
                return SimpleNamespace(
                    employee_name=employee_name,
                    employee_user_id="mgr-1",
                    manager_name="Сидоров Сидор Сидорович",
                    manager_user_id="top-1",
                    department_name="Руководство",
                    schedule_name="Пятидневка - Девушки 08:30-12:30 / 14:00-17:15",
                    schedule_id="ГР003",
                    role="manager",
                    is_active=True,
                )
            if employee_name == "Кадрова Анна Сергеевна":
                return SimpleNamespace(
                    employee_name=employee_name,
                    employee_user_id="hr-1",
                    manager_name="Сидоров Сидор Сидорович",
                    manager_user_id="top-1",
                    department_name="HR",
                    schedule_name="Пятидневка - Девушки 08:30-12:30 / 14:00-17:15",
                    schedule_id="ГР003",
                    role="hr",
                    is_active=True,
                )
            return None

        with patch("app.services.skud_import.AttendanceCaseRepository", _FakeAttendanceCaseRepository), patch(
            "app.services.skud_import.ApprovalRepository", _FakeApprovalRepository
        ), patch(
            "app.services.skud_import.EmployeeDirectoryRepository", _FakeEmployeeDirectoryRepository
        ), patch(
            "app.services.skud_import.SkudImportRepository", _FakeSkudImportRepository
        ), patch(
            "app.services.skud_import.AttendanceDayRecordRepository", lambda: day_repo
        ), patch(
            "app.services.skud_import.GoogleSheetsDirectoryService.from_settings",
            return_value=SimpleNamespace(get_by_employee_name=_directory_lookup),
        ), patch(
            "app.services.skud_import.GoogleSheetsScheduleService.from_settings",
            return_value=_FakeGoogleSheetsScheduleService(),
        ), patch(
            "app.services.skud_import.SubstitutionRepository",
            return_value=_FakeSubstitutionRepository(),
        ):
            service = SkudImportService()
            result = service.import_csv(filename="report.txt", content=access_report, created_by_user_id="sec_001")

        self.assertEqual(result.error_rows, 0)
        self.assertEqual(result.unique_employees, 2)
        self.assertEqual(len(day_repo.rows), 2)
        self.assertEqual({row["employee_user_id"] for row in day_repo.rows}, {"mgr-1", "hr-1"})
        self.assertEqual(len(service.case_repository.created), 2)

    def test_employee_summary_report_import_parses_daily_stats_and_cases(self) -> None:
        summary_report = (
            "О сотруднике: c 11.05.2026 по 12.05.2026\n"
            "\n"
            "\n"
            "\n"
            "Фирма;Подразделение;Сотрудник;Должность;Таб. №;Дата;Находился в здании;Опоздал;Вечерняя переработка;Ранних уходов;Прогулял;Причины не выхода;Комм. причины отсутствия;Утренняя переработка;Ранних уходов в теч. дня;Опозданий в теч. дня;Мягких прогулов;Начало дня;Конец дня;Работа в выходной день;Работа в праздничные дни;Все переработки;Фактическая переработка\n"
            "ФНС;Отдел продаж;Иванова Анна Сергеевна;;;11.05.2026;0.2708333333333333;0.0097222222222222;0.0104166666666667;0;0;;;0;0;0;0;08:44;17:30;0;0;0;0:15\n"
            "ФНС;Отдел продаж;Иванова Анна Сергеевна;;;12.05.2026;0;0;0;0;0.3020833333333333;;;0;0;0;0;Нет входа (0:00);Нет выхода (23:59);0;0;0;-7:15\n"
        ).encode("utf-8")

        day_repo = _FakeAttendanceDayRecordRepository()

        with patch("app.services.skud_import.AttendanceCaseRepository", _FakeAttendanceCaseRepository), patch(
            "app.services.skud_import.ApprovalRepository", _FakeApprovalRepository
        ), patch(
            "app.services.skud_import.EmployeeDirectoryRepository", _FakeEmployeeDirectoryRepository
        ), patch(
            "app.services.skud_import.SkudImportRepository", _FakeSkudImportRepository
        ), patch(
            "app.services.skud_import.AttendanceDayRecordRepository", lambda: day_repo
        ), patch(
            "app.services.skud_import.GoogleSheetsDirectoryService.from_settings",
            return_value=SimpleNamespace(
                get_by_employee_name=lambda employee_name: SimpleNamespace(
                    employee_name=employee_name,
                    employee_user_id="max_010",
                    manager_name="Петров Петр Сергеевич",
                    manager_user_id="max_020",
                    department_name="Отдел продаж",
                    schedule_name="Пятидневка - Девушки 08:30-12:30 / 14:00-17:15",
                    schedule_id="ГР003",
                    role="employee",
                    is_active=True,
                )
            ),
        ), patch(
            "app.services.skud_import.GoogleSheetsScheduleService.from_settings",
            return_value=_FakeGoogleSheetsScheduleService(),
        ), patch(
            "app.services.skud_import.SubstitutionRepository",
            return_value=_FakeSubstitutionRepository(),
        ):
            service = SkudImportService()
            result = service.import_csv(filename="summary.xlsx", content=summary_report, created_by_user_id="sec_001")

        self.assertEqual(result.error_rows, 0)
        self.assertEqual(result.total_rows, 2)
        self.assertEqual(result.unique_employees, 1)
        self.assertEqual(result.created_cases, 2)
        self.assertEqual(result.period_start, "2026-05-11")
        self.assertEqual(result.period_end, "2026-05-12")
        self.assertEqual(result.arrivals_late, 1)
        self.assertEqual(result.departures_late, 1)
        self.assertEqual(len(day_repo.rows), 2)
        self.assertEqual({row["source"] for row in day_repo.rows}, {"skud_employee_summary"})
        first_row = next(row for row in day_repo.rows if row["event_date"] == "2026-05-11")
        self.assertEqual(first_row["first_entry_time"], "08:44")
        self.assertEqual(first_row["last_exit_time"], "17:30")
        self.assertEqual(first_row["arrival_status"], "late")
        self.assertEqual(first_row["departure_status"], "late")
        self.assertEqual(first_row["lunch_minutes"], 90)
        self.assertEqual(first_row["balance_minutes"], 15)
        self.assertEqual(first_row["late_compensated"], True)
        second_row = next(row for row in day_repo.rows if row["event_date"] == "2026-05-12")
        self.assertEqual(second_row["arrival_status"], "")
        self.assertEqual(second_row["departure_status"], "")
        self.assertEqual(second_row["worked_minutes"], 0)
        self.assertEqual(second_row["balance_minutes"], -429)
        created_case_types = {row["case_type"] for row in service.case_repository.created}
        self.assertEqual(created_case_types, {"late", "absent"})

    def test_violation_report_import_accepts_excel_serial_times(self) -> None:
        violation_report = (
            "Отчет о нарушениях: c 25.05.2026 по 25.05.2026\n"
            ";г. Салехард, ул. Губкина, д.6 «А»\n"
            "Фирма;Подразделение;Сотрудник;Должность;Таб. №;Дата;Опоздал;"
            "Время ухода на обед;Ранних уходов в теч. дня;Время прихода с обеда;"
            "Опозданий в теч. дня;Ранних уходов;Прогулял;Причины не выхода;"
            "Комм. причины отсутствия;Начало дня;Конец дня\n"
            "ФНС;Отдел продаж;Иванова Анна Сергеевна;;;25.05.2026;"
            "0.020833333333333332;0.5125;0;0.5895833333333333;0;0;"
            "0;;;0.32777777777777778;0.7055555555555556\n"
        ).encode("utf-8")
        day_repo = _FakeAttendanceDayRecordRepository()

        with patch("app.services.skud_import.AttendanceCaseRepository", _FakeAttendanceCaseRepository), patch(
            "app.services.skud_import.ApprovalRepository", _FakeApprovalRepository
        ), patch(
            "app.services.skud_import.EmployeeDirectoryRepository", _FakeEmployeeDirectoryRepository
        ), patch(
            "app.services.skud_import.SkudImportRepository", _FakeSkudImportRepository
        ), patch(
            "app.services.skud_import.AttendanceDayRecordRepository", lambda: day_repo
        ), patch(
            "app.services.skud_import.GoogleSheetsDirectoryService.from_settings",
            return_value=SimpleNamespace(
                get_by_employee_name=lambda employee_name: SimpleNamespace(
                    employee_name=employee_name,
                    employee_user_id="max_010",
                    manager_name="Петров Петр Сергеевич",
                    manager_user_id="max_020",
                    department_name="Отдел продаж",
                    schedule_name="Пятидневка - Девушки 08:30-12:30 / 14:00-17:15",
                    schedule_id="ГР003",
                    role="employee",
                    is_active=True,
                )
            ),
        ), patch(
            "app.services.skud_import.GoogleSheetsScheduleService.from_settings",
            return_value=_FakeGoogleSheetsScheduleService(),
        ), patch(
            "app.services.skud_import.SubstitutionRepository",
            return_value=_FakeSubstitutionRepository(),
        ):
            service = SkudImportService()
            result = service.import_csv(
                filename="ОП 1.xlsx",
                content=violation_report,
                created_by_user_id="manager_001",
            )

        self.assertEqual(result.error_rows, 0)
        self.assertEqual(result.total_rows, 1)
        self.assertEqual(result.unique_employees, 1)
        self.assertEqual(result.period_start, "2026-05-25")
        self.assertEqual(result.period_end, "2026-05-25")
        self.assertEqual(len(day_repo.rows), 1)
        self.assertEqual(day_repo.rows[0]["first_entry_time"], "07:52")
        self.assertEqual(day_repo.rows[0]["last_exit_time"], "16:56")
        self.assertEqual(day_repo.rows[0]["arrival_status"], "late")

    def test_employee_summary_report_falls_back_to_clock_times_when_summary_minutes_are_zero(self) -> None:
        summary_report = (
            "О сотруднике: c 15.05.2026 по 15.05.2026\n"
            "\n"
            "\n"
            "\n"
            "Фирма;Подразделение;Сотрудник;Должность;Таб. №;Дата;Находился в здании;Опоздал;Вечерняя переработка;Ранних уходов;Прогулял;Причины не выхода;Комм. причины отсутствия;Утренняя переработка;Ранних уходов в теч. дня;Опозданий в теч. дня;Мягких прогулов;Начало дня;Конец дня;Работа в выходной день;Работа в праздничные дни;Все переработки;Фактическая переработка\n"
            "ФНС;15-ОНК№1;Баженов Станислав Сергеевич;;;15.05.2026;0.0638888888888889;0;0;0;0;;;0;0;0;0;16:46;17:08;0;0;0;-6:43\n"
        ).encode("utf-8")

        day_repo = _FakeAttendanceDayRecordRepository()

        with patch("app.services.skud_import.AttendanceCaseRepository", _FakeAttendanceCaseRepository), patch(
            "app.services.skud_import.ApprovalRepository", _FakeApprovalRepository
        ), patch(
            "app.services.skud_import.EmployeeDirectoryRepository", _FakeEmployeeDirectoryRepository
        ), patch(
            "app.services.skud_import.SkudImportRepository", _FakeSkudImportRepository
        ), patch(
            "app.services.skud_import.AttendanceDayRecordRepository", lambda: day_repo
        ), patch(
            "app.services.skud_import.GoogleSheetsDirectoryService.from_settings",
            return_value=SimpleNamespace(
                get_by_employee_name=lambda employee_name: SimpleNamespace(
                    employee_name=employee_name,
                    employee_user_id="max_260",
                    manager_name="Марникова Наталья Евгеньевна",
                    manager_user_id="max_mgr_260",
                    department_name="15-ОНК№1",
                    schedule_name="Пятидневка - Девушки 08:30-12:30 / 14:00-17:15",
                    schedule_id="ГР003",
                    role="employee",
                    is_active=True,
                )
            ),
        ), patch(
            "app.services.skud_import.GoogleSheetsScheduleService.from_settings",
            return_value=_FakeGoogleSheetsScheduleService(),
        ), patch(
            "app.services.skud_import.SubstitutionRepository",
            return_value=_FakeSubstitutionRepository(),
        ):
            service = SkudImportService()
            result = service.import_csv(filename="summary.xlsx", content=summary_report, created_by_user_id="sec_001")

        self.assertEqual(result.error_rows, 0)
        self.assertEqual(result.arrivals_late, 1)
        self.assertEqual(result.departures_early, 1)
        self.assertEqual(len(day_repo.rows), 1)
        row = day_repo.rows[0]
        self.assertEqual(row["first_entry_time"], "16:46")
        self.assertEqual(row["arrival_status"], "late")
        self.assertEqual(row["arrival_delta_minutes"], 496)
        self.assertEqual(row["last_exit_time"], "17:08")
        self.assertEqual(row["departure_status"], "early")
        self.assertEqual(row["departure_delta_minutes"], -7)

    def test_employee_summary_report_infers_planned_minutes_and_lunch_from_schedule_when_missing(self) -> None:
        summary_report = (
            "О сотруднике: c 15.05.2026 по 15.05.2026\n"
            "\n"
            "\n"
            "\n"
            "Фирма;Подразделение;Сотрудник;Должность;Таб. №;Дата;Находился в здании;Опоздал;Вечерняя переработка;Ранних уходов;Прогулял;Причины не выхода;Комм. причины отсутствия;Утренняя переработка;Ранних уходов в теч. дня;Опозданий в теч. дня;Мягких прогулов;Начало дня;Конец дня;Работа в выходной день;Работа в праздничные дни;Все переработки;Фактическая переработка\n"
            "ФНС;15-ОНК№1;Тестов Тест Тестович;;;15.05.2026;0.3645833333333333;0;0;0;0;;;0;0;0;0;08:30;17:15;0;0;0;0\n"
        ).encode("utf-8")

        day_repo = _FakeAttendanceDayRecordRepository()

        with patch("app.services.skud_import.AttendanceCaseRepository", _FakeAttendanceCaseRepository), patch(
            "app.services.skud_import.ApprovalRepository", _FakeApprovalRepository
        ), patch(
            "app.services.skud_import.EmployeeDirectoryRepository", _FakeEmployeeDirectoryRepository
        ), patch(
            "app.services.skud_import.SkudImportRepository", _FakeSkudImportRepository
        ), patch(
            "app.services.skud_import.AttendanceDayRecordRepository", lambda: day_repo
        ), patch(
            "app.services.skud_import.GoogleSheetsDirectoryService.from_settings",
            return_value=SimpleNamespace(
                get_by_employee_name=lambda employee_name: SimpleNamespace(
                    employee_name=employee_name,
                    employee_user_id="max_999",
                    manager_name="Руководитель",
                    manager_user_id="mgr_999",
                    department_name="15-ОНК№1",
                    schedule_name="Fallback schedule",
                    schedule_id="FALLBACK",
                    role="employee",
                    is_active=True,
                )
            ),
        ), patch(
            "app.services.skud_import.GoogleSheetsScheduleService.from_settings",
            return_value=_FallbackScheduleService(),
        ), patch(
            "app.services.skud_import.SubstitutionRepository",
            return_value=_FakeSubstitutionRepository(),
        ):
            service = SkudImportService()
            result = service.import_csv(filename="summary.xlsx", content=summary_report, created_by_user_id="sec_001")

        self.assertEqual(result.error_rows, 0)
        self.assertEqual(len(day_repo.rows), 1)
        row = day_repo.rows[0]
        self.assertEqual(row["planned_minutes"], 435)
        self.assertEqual(row["lunch_minutes"], 90)
        self.assertEqual(row["worked_minutes"], 435)
        self.assertEqual(row["balance_minutes"], 0)

    def test_employee_summary_treats_2359_exit_as_absence_not_overtime(self) -> None:
        summary_report = (
            "О сотруднике: c 15.05.2026 по 15.05.2026\n"
            "\n"
            "\n"
            "\n"
            "Фирма;Подразделение;Сотрудник;Должность;Таб. №;Дата;Находился в здании;Опоздал;Вечерняя переработка;Ранних уходов;Прогулял;Причины не выхода;Комм. причины отсутствия;Утренняя переработка;Ранних уходов в теч. дня;Опозданий в теч. дня;Мягких прогулов;Начало дня;Конец дня;Работа в выходной день;Работа в праздничные дни;Все переработки;Фактическая переработка\n"
            "ФНС;Отдел продаж;Иванова Анна Сергеевна;;;12.05.2026;0.6458333333333334;0;0.2708333333333333;0;0;;;0;0;0;0;08:30;23:59;0;0;0;6:30\n"
        ).encode("utf-8")

        day_repo = _FakeAttendanceDayRecordRepository()

        with patch("app.services.skud_import.AttendanceCaseRepository", _FakeAttendanceCaseRepository), patch(
            "app.services.skud_import.ApprovalRepository", _FakeApprovalRepository
        ), patch(
            "app.services.skud_import.EmployeeDirectoryRepository", _FakeEmployeeDirectoryRepository
        ), patch(
            "app.services.skud_import.SkudImportRepository", _FakeSkudImportRepository
        ), patch(
            "app.services.skud_import.AttendanceDayRecordRepository", lambda: day_repo
        ), patch(
            "app.services.skud_import.GoogleSheetsDirectoryService.from_settings",
            return_value=SimpleNamespace(
                get_by_employee_name=lambda employee_name: SimpleNamespace(
                    employee_name=employee_name,
                    employee_user_id="max_010",
                    manager_name="Петров Петр Сергеевич",
                    manager_user_id="max_020",
                    department_name="Отдел продаж",
                    schedule_name="Пятидневка - Девушки 08:30-12:30 / 14:00-17:15",
                    schedule_id="ГР003",
                    role="employee",
                    is_active=True,
                )
            ),
        ), patch(
            "app.services.skud_import.GoogleSheetsScheduleService.from_settings",
            return_value=_FakeGoogleSheetsScheduleService(),
        ), patch(
            "app.services.skud_import.SubstitutionRepository",
            return_value=_FakeSubstitutionRepository(),
        ):
            service = SkudImportService()
            result = service.import_csv(filename="summary.xlsx", content=summary_report, created_by_user_id="sec_001")

        self.assertEqual(result.error_rows, 0)
        self.assertEqual(result.created_cases, 1)
        self.assertEqual(service.case_repository.created[0]["case_type"], "absent")
        self.assertEqual(len(day_repo.rows), 1)
        row = day_repo.rows[0]
        self.assertEqual(row["last_exit_time"], "")
        self.assertEqual(row["departure_status"], "")
        self.assertEqual(row["worked_minutes"], 0)
        self.assertEqual(row["balance_minutes"], -429)

    def test_access_report_marks_late_as_compensated_when_weekly_balance_covers_delay(self) -> None:
        access_report = (
            "Отчет по проходам\n"
            "Ф.И.О;Таб.№;Подразделение;Подразделение;Дата и время;Точка;Событие;Зона\n"
            "Иванова Анна Сергеевна;;;Отдел продаж;04.05.2026 08:44:00;Вход;Проход;Здание\n"
            "Иванова Анна Сергеевна;;;Отдел продаж;04.05.2026 17:40:00;Выход;Проход;Внешний мир\n"
        ).encode("utf-8")

        day_repo = _FakeAttendanceDayRecordRepository()

        with patch("app.services.skud_import.AttendanceCaseRepository", _FakeAttendanceCaseRepository), patch(
            "app.services.skud_import.ApprovalRepository", _FakeApprovalRepository
        ), patch(
            "app.services.skud_import.EmployeeDirectoryRepository", _FakeEmployeeDirectoryRepository
        ), patch(
            "app.services.skud_import.SkudImportRepository", _FakeSkudImportRepository
        ), patch(
            "app.services.skud_import.AttendanceDayRecordRepository", lambda: day_repo
        ), patch(
            "app.services.skud_import.GoogleSheetsDirectoryService.from_settings",
            return_value=SimpleNamespace(
                get_by_employee_name=lambda employee_name: SimpleNamespace(
                    employee_name=employee_name,
                    employee_user_id="max_010",
                    manager_name="Петров Петр Сергеевич",
                    manager_user_id="max_020",
                    department_name="Отдел продаж",
                    schedule_name="Пятидневка - Девушки 08:30-12:30 / 14:00-17:15",
                    schedule_id="ГР003",
                    role="employee",
                    is_active=True,
                )
            ),
        ), patch(
            "app.services.skud_import.GoogleSheetsScheduleService.from_settings",
            return_value=_FakeGoogleSheetsScheduleService(),
        ), patch(
            "app.services.skud_import.SubstitutionRepository",
            return_value=_FakeSubstitutionRepository(),
        ):
            service = SkudImportService()
            result = service.import_csv(filename="report.txt", content=access_report, created_by_user_id="sec_001")

        self.assertEqual(result.error_rows, 0)
        self.assertEqual(len(day_repo.rows), 1)
        row = day_repo.rows[0]
        self.assertEqual(row["arrival_status"], "late")
        self.assertEqual(row["arrival_delta_minutes"], 14)
        self.assertEqual(row["balance_minutes"], 17)
        self.assertEqual(row["late_compensated"], True)

    def test_access_report_skips_top_manager_role(self) -> None:
        access_report = (
            "Отчет по проходам\n"
            "Ф.И.О;Таб.№;Подразделение;Подразделение;Дата и время;Точка;Событие;Зона\n"
            "Посунько Руслан Юрьевич;;;Топ-руководство;04.05.2026 08:44:00;Вход;Проход;Здание\n"
        ).encode("utf-8")

        day_repo = _FakeAttendanceDayRecordRepository()

        with patch("app.services.skud_import.AttendanceCaseRepository", _FakeAttendanceCaseRepository), patch(
            "app.services.skud_import.ApprovalRepository", _FakeApprovalRepository
        ), patch(
            "app.services.skud_import.EmployeeDirectoryRepository", _FakeEmployeeDirectoryRepository
        ), patch(
            "app.services.skud_import.SkudImportRepository", _FakeSkudImportRepository
        ), patch(
            "app.services.skud_import.AttendanceDayRecordRepository", lambda: day_repo
        ), patch(
            "app.services.skud_import.GoogleSheetsDirectoryService.from_settings",
            return_value=SimpleNamespace(
                get_by_employee_name=lambda employee_name: SimpleNamespace(
                    employee_name=employee_name,
                    employee_user_id="top-1",
                    manager_name="",
                    manager_user_id="",
                    department_name="Топ-руководство",
                    schedule_name="Пятидневка - Девушки 08:30-12:30 / 14:00-17:15",
                    schedule_id="ГР003",
                    role="top_manager",
                    is_active=True,
                )
            ),
        ), patch(
            "app.services.skud_import.GoogleSheetsScheduleService.from_settings",
            return_value=_FakeGoogleSheetsScheduleService(),
        ), patch(
            "app.services.skud_import.SubstitutionRepository",
            return_value=_FakeSubstitutionRepository(),
        ):
            service = SkudImportService()
            result = service.import_csv(filename="report.txt", content=access_report, created_by_user_id="sec_001")

        self.assertEqual(result.error_rows, 0)
        self.assertEqual(result.unique_employees, 0)
        self.assertEqual(len(day_repo.rows), 0)
        self.assertEqual(service.case_repository.created, [])


if __name__ == "__main__":
    unittest.main()
