from __future__ import annotations

import unittest
from types import SimpleNamespace

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


class _FakeLocalDirectoryRepository:
    def __init__(self, rows=None):
        self.rows = rows or []

    def get_by_user_id(self, user_id: str):
        for row in self.rows:
            if row.employee_user_id == user_id:
                return row
        return None

    def get_by_employee_name(self, employee_name: str):
        for row in self.rows:
            if row.employee_name == employee_name:
                return row
        return None


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

    def test_my_manager_displays_manager_name_from_manager_user_id(self) -> None:
        router = MaxWebhookRouter()
        router.employee_directory_repository = _FakeLocalDirectoryRepository(
            [
                SimpleNamespace(
                    employee_name="Иванов Иван Иванович",
                    employee_user_id="max_001",
                    manager_name="Старое Имя Руководителя",
                    manager_user_id="max_002",
                    department_name="Отдел продаж",
                    role="employee",
                    is_active=True,
                ),
                SimpleNamespace(
                    employee_name="Петров Петр Сергеевич",
                    employee_user_id="max_002",
                    manager_name="",
                    manager_user_id="",
                    department_name="Отдел продаж",
                    role="manager",
                    is_active=True,
                ),
            ]
        )

        response = router._my_manager("employee", "max_001")

        self.assertIn("Петров Петр Сергеевич", response.outbound.text)
        self.assertNotIn("Старое Имя Руководителя", response.outbound.text)

    def test_late_notice_manager_options_prefers_manager_id_name(self) -> None:
        router = MaxWebhookRouter()
        router.employee_directory_repository = _FakeLocalDirectoryRepository(
            [
                SimpleNamespace(
                    employee_name="Петров Петр Сергеевич",
                    employee_user_id="max_002",
                    manager_name="",
                    manager_user_id="",
                    department_name="Отдел продаж",
                    role="manager",
                    is_active=True,
                ),
            ]
        )
        employee = SimpleNamespace(
            manager_name="Старое Имя Руководителя",
            manager_user_id="max_002",
            department_name="Отдел продаж",
        )

        self.assertEqual(
            router._build_late_notice_manager_options(employee, "employee"),
            [("max_002", "Петров Петр Сергеевич")],
        )


if __name__ == "__main__":
    unittest.main()
