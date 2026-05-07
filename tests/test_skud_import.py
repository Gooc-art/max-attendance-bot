from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.skud_import import SkudImportService


class _FakeAttendanceCaseRepository:
    def __init__(self):
        self.created = []

    def create_case(self, **kwargs):
        self.created.append(kwargs)
        return len(self.created)


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
            "app.services.skud_import.GoogleSheetsDirectoryService.from_settings",
            return_value=_FakeGoogleSheetsDirectoryService(),
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
        ):
            service = SkudImportService()
            result = service.import_csv(filename="report.txt", content=access_report, created_by_user_id="sec_001")

        self.assertEqual(result.created_cases, 1)
        created_case = service.case_repository.created[0]
        self.assertEqual(created_case["planned_start"], "08:30")
        self.assertEqual(created_case["delay_minutes"], 14)
        self.assertEqual(result.period_start, "2026-05-04")
        self.assertEqual(result.period_end, "2026-05-04")


if __name__ == "__main__":
    unittest.main()
