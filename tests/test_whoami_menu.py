from __future__ import annotations

import unittest

from app.bot.router import MaxWebhookRouter
from app.integrations.google_sheets.directory import GoogleSheetsEmployeeRecord


class _FakeGoogleDirectoryService:
    def __init__(self, record=None, configured: bool = True):
        self.record = record
        self.configured = configured

    def get_by_user_id(self, user_id: str, refresh: bool = False):
        return self.record

    def is_configured(self) -> bool:
        return self.configured


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

        self.assertIn("Твой ID в MAX: 203302812", response.outbound.text)
        self.assertIn("Роль в боте: Администратор", response.outbound.text)
        self.assertIn("Найдено в Google Sheets", response.outbound.text)
        self.assertIn("Нужный ID для таблицы: 203302812", response.outbound.text)

    def test_whoami_reports_unconfigured_google_sheets_runtime(self) -> None:
        router = MaxWebhookRouter()
        router.google_directory_service = _FakeGoogleDirectoryService(record=None, configured=False)

        response = router._whoami("employee", "23325864", "296369649")

        self.assertIn("Google Sheets в этой runtime-среде не настроен", response.outbound.text)
        self.assertIn("это не означает, что записи нет", response.outbound.text)
        self.assertNotIn("запись не найдена", response.outbound.text)


if __name__ == "__main__":
    unittest.main()
