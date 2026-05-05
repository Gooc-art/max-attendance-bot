from __future__ import annotations

import unittest

from app.bot.router import MaxWebhookRouter
from app.integrations.google_sheets.directory import GoogleSheetsEmployeeRecord


class _FakeGoogleDirectoryService:
    def __init__(self, record=None):
        self.record = record

    def get_by_user_id(self, user_id: str, refresh: bool = False):
        return self.record


class AdminRowAndBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = MaxWebhookRouter()

    def test_my_row_shows_sheet_details(self) -> None:
        self.router.google_directory_service = _FakeGoogleDirectoryService(
            GoogleSheetsEmployeeRecord(
                employee_name="Кутлуев Родион Романович",
                employee_user_id="203302812",
                manager_name="Петров Петр Сергеевич",
                manager_user_id="101",
                department_name="ИТ",
                role="admin",
                is_active=True,
            )
        )

        response = self.router._my_row("admin", "203302812")

        self.assertIn("Моя строка", response.outbound.text)
        self.assertIn("Кутлуев Родион Романович", response.outbound.text)
        self.assertIn("203302812", response.outbound.text)
        self.assertIn("Роль: Администратор", response.outbound.text)
        self.assertIn("ИТ", response.outbound.text)

    def test_binding_check_shows_match_status(self) -> None:
        self.router.google_directory_service = _FakeGoogleDirectoryService(
            GoogleSheetsEmployeeRecord(
                employee_name="Кутлуев Родион Романович",
                employee_user_id="203302812",
                manager_name="Петров Петр Сергеевич",
                manager_user_id="101",
                department_name="ИТ",
                role="admin",
                is_active=True,
            )
        )

        response = self.router._binding_check("admin", "203302812")

        self.assertIn("Привязка найдена", response.outbound.text)
        self.assertIn("Роль: Администратор", response.outbound.text)
        self.assertIn("Совпадение: Да", response.outbound.text)


if __name__ == "__main__":
    unittest.main()
