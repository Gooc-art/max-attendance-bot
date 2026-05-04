from __future__ import annotations

import unittest
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


if __name__ == "__main__":
    unittest.main()
