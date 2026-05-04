from __future__ import annotations

import unittest
from unittest.mock import patch

from app.api.routes.employee_directory import list_employee_directory
from app.integrations.google_sheets.directory import GoogleSheetsEmployeeRecord


class _FakeGoogleDirectoryService:
    def __init__(self, records):
        self.records = records

    def list_employees(self, refresh: bool = False):
        return list(self.records)


class EmployeeDirectoryRouteTests(unittest.TestCase):
    def test_google_sheet_is_returned_when_available(self) -> None:
        records = [
            GoogleSheetsEmployeeRecord(
                employee_name="Иванов Иван Иванович",
                employee_user_id="max_001",
                manager_name="Петров Петр Сергеевич",
                manager_user_id="max_002",
                department_name="Отдел продаж",
                role="admin",
                is_active=True,
            )
        ]
        with patch(
            "app.api.routes.employee_directory.GoogleSheetsDirectoryService.from_settings",
            return_value=_FakeGoogleDirectoryService(records),
        ):
            result = list_employee_directory(limit=1)

        self.assertEqual(result["source"], "google_sheets")
        self.assertEqual(result["items"][0]["employee_user_id"], "max_001")
        self.assertEqual(result["items"][0]["role"], "admin")


if __name__ == "__main__":
    unittest.main()
