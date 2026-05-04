from __future__ import annotations

import unittest

from app.bot.router import MaxWebhookRouter
from app.integrations.google_sheets.directory import GoogleSheetsEmployeeRecord


class _FakeGoogleDirectoryService:
    def __init__(self, manager_record=None, rows=None):
        self.manager_record = manager_record
        self.rows = rows or []

    def get_by_user_id(self, user_id: str, refresh: bool = False):
        return self.manager_record

    def get_by_manager_user_id(self, manager_user_id: str, refresh: bool = False):
        return list(self.rows)

    def list_employees(self, refresh: bool = False):
        return list(self.rows)


class RouterDirectorySourceTests(unittest.TestCase):
    def test_my_manager_uses_google_sheet_first(self) -> None:
        router = MaxWebhookRouter()
        router.google_directory_service = _FakeGoogleDirectoryService(
            manager_record=GoogleSheetsEmployeeRecord(
                employee_name="Иванов Иван Иванович",
                employee_user_id="max_001",
                manager_name="Петров Петр Сергеевич",
                manager_user_id="max_002",
                department_name="Отдел продаж",
                role="employee",
                is_active=True,
            )
        )

        response = router._my_manager("employee", "max_001")

        self.assertIn("Петров Петр Сергеевич", response.outbound.text)
        self.assertIn("Отдел продаж", response.outbound.text)


if __name__ == "__main__":
    unittest.main()
