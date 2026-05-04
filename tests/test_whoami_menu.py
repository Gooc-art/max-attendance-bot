from __future__ import annotations

import unittest

from app.bot.router import MaxWebhookRouter
from app.integrations.google_sheets.directory import GoogleSheetsEmployeeRecord


class _FakeGoogleDirectoryService:
    def __init__(self, record=None):
        self.record = record

    def get_by_user_id(self, user_id: str, refresh: bool = False):
        return self.record


class WhoAmITests(unittest.TestCase):
    def test_whoami_shows_user_id_and_sheet_match(self) -> None:
        router = MaxWebhookRouter()
        router.google_directory_service = _FakeGoogleDirectoryService(
            GoogleSheetsEmployeeRecord(
                employee_name="Кутлуев Родион Романович",
                employee_user_id="203302812",
                manager_name="",
                manager_user_id="",
                department_name="",
                role="admin",
                is_active=True,
            )
        )

        response = router._whoami("admin", "203302812", "123")

        self.assertIn("user_id из MAX: 203302812", response.outbound.text)
        self.assertIn("Роль, которую видит бот: admin", response.outbound.text)
        self.assertIn("Найдено в Google Sheets", response.outbound.text)
        self.assertIn("Нужный ID: 203302812", response.outbound.text)


if __name__ == "__main__":
    unittest.main()
