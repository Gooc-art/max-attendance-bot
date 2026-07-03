from __future__ import annotations

import unittest

from app.bot.router import MaxWebhookRouter
from app.integrations.google_sheets.directory import GoogleSheetsEmployeeRecord


class _FakeGoogleDirectoryService:
    def __init__(self, record=None, configured: bool = True):
        self.record = record
        self.configured = configured
        self.calls = 0

    def get_by_user_id(self, user_id: str, refresh: bool = False):
        self.calls += 1
        return self.record

    def is_configured(self) -> bool:
        return self.configured


class WhoAmITests(unittest.TestCase):
    def test_whoami_uses_local_directory_before_google_sheets(self) -> None:
        router = MaxWebhookRouter()
        router.google_directory_service = _FakeGoogleDirectoryService(
            GoogleSheetsEmployeeRecord(employee_name="Медленная Google запись", employee_user_id="203302812")
        )
        router.employee_directory_repository.get_by_user_id = lambda user_id: GoogleSheetsEmployeeRecord(
            employee_name="Быстрая локальная запись",
            employee_user_id=user_id,
            department_name="Отдел",
            office="314",
            role="manager",
            is_active=True,
        )

        response = router._whoami("manager", "203302812", "123")

        self.assertIn("Найдено в локальном справочнике", response.outbound.text)
        self.assertIn("ФИО: Быстрая локальная запись", response.outbound.text)
        self.assertEqual(router.google_directory_service.calls, 0)

    def test_whoami_shows_user_id_and_sheet_match(self) -> None:
        router = MaxWebhookRouter()
        router.employee_directory_repository.get_by_user_id = lambda user_id: None
        router.google_directory_service = _FakeGoogleDirectoryService(
            GoogleSheetsEmployeeRecord(
                employee_name="Кутлуев Родион Романович",
                employee_user_id="203302812",
                manager_name="",
                manager_user_id="",
                department_name="0.1. Зам_руководителя",
                office="314",
                role="admin",
                is_active=True,
            )
        )

        response = router._whoami("admin", "203302812", "123")

        self.assertIn("Твой ID в MAX: 203302812", response.outbound.text)
        self.assertIn("Роль в боте: Администратор", response.outbound.text)
        self.assertIn("Найдено в Google Sheets", response.outbound.text)
        self.assertIn("ФИО: Кутлуев Родион Романович\nПодразделение: 0.1. Зам_руководителя\nКабинет: 314", response.outbound.text)
        self.assertIn("Нужный ID для таблицы: 203302812", response.outbound.text)

    def test_whoami_normalizes_manager_role_from_sheet_label(self) -> None:
        router = MaxWebhookRouter()
        router.employee_directory_repository.get_by_user_id = lambda user_id: None
        router.google_directory_service = _FakeGoogleDirectoryService(
            GoogleSheetsEmployeeRecord(
                employee_name="Лебедев Тест",
                employee_user_id="23325864",
                department_name="Отдел",
                role="Руководитель",
                is_active=True,
            )
        )

        response = router._whoami("manager", "23325864", "296369649")

        self.assertIn("Роль в боте: Начальник отдела", response.outbound.text)
        self.assertIn("Роль в таблице: Начальник отдела", response.outbound.text)
        self.assertNotIn("Роль в таблице: Руководитель", response.outbound.text)

    def test_whoami_reports_unconfigured_google_sheets_runtime(self) -> None:
        router = MaxWebhookRouter()
        router.employee_directory_repository.get_by_user_id = lambda user_id: None
        router.google_directory_service = _FakeGoogleDirectoryService(record=None, configured=False)

        response = router._whoami("employee", "23325864", "296369649")

        self.assertIn("Google Sheets в этой runtime-среде не настроен", response.outbound.text)
        self.assertIn("это не означает, что записи нет", response.outbound.text)
        self.assertNotIn("запись не найдена", response.outbound.text)


if __name__ == "__main__":
    unittest.main()
