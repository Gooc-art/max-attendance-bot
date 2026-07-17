from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.bot.actions import BotAction
from app.bot.router import MaxWebhookRouter
from app.domain.enums import Role
from app.domain.role_labels import display_role_name
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
        router.user_bot_activity_repository.get_by_user_id = MagicMock(return_value=None)
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
        router.user_bot_activity_repository.get_by_user_id = MagicMock(return_value=None)
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
        self.assertEqual(response.outbound.buttons[0].action, BotAction.MENU_ADMIN_PANEL)
        self.assertEqual(response.outbound.buttons[1].action, BotAction.WHOAMI)

    def test_whoami_shows_device_status_and_detection_text_link(self) -> None:
        router = MaxWebhookRouter()
        router.employee_directory_repository.get_by_user_id = lambda user_id: None
        router.google_directory_service = _FakeGoogleDirectoryService(record=None, configured=True)
        router.user_bot_activity_repository.get_by_user_id = MagicMock(
            return_value=type("Activity", (), {"device_platform": "android"})()
        )

        with patch("app.bot.router.get_settings") as get_settings:
            get_settings.return_value.public_base_url = "https://demo.lhr.life/api/webhooks/max"
            response = router._whoami("employee", "203302812", "123")

        self.assertIn("Устройство: Android", response.outbound.text)
        self.assertIn("Определить устройство: https://demo.lhr.life/device?user_id=203302812", response.outbound.text)
        self.assertLess(response.outbound.text.index("Устройство: Android"), response.outbound.text.index("Твой ID в MAX"))
        button = response.outbound.buttons[0]
        self.assertEqual(button.title, "Обновить")

    def test_whoami_normalizes_manager_role_from_sheet_label(self) -> None:
        router = MaxWebhookRouter()
        router.user_bot_activity_repository.get_by_user_id = MagicMock(return_value=None)
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
        router.user_bot_activity_repository.get_by_user_id = MagicMock(return_value=None)
        router.employee_directory_repository.get_by_user_id = lambda user_id: None
        router.google_directory_service = _FakeGoogleDirectoryService(record=None, configured=False)

        response = router._whoami("employee", "23325864", "296369649")

        self.assertIn("Google Sheets в этой runtime-среде не настроен", response.outbound.text)
        self.assertIn("это не означает, что записи нет", response.outbound.text)
        self.assertNotIn("запись не найдена", response.outbound.text)

    def test_whoami_result_matches_each_bot_role(self) -> None:
        for role in Role:
            with self.subTest(role=role.value):
                router = MaxWebhookRouter()
                router.user_bot_activity_repository.get_by_user_id = MagicMock(return_value=None)
                router.employee_directory_repository.get_by_user_id = lambda user_id, role=role: GoogleSheetsEmployeeRecord(
                    employee_name="Тест Пользователь",
                    employee_user_id=user_id,
                    role=role.value,
                    is_active=True,
                )

                response = router._whoami(role.value, "23325864", "296369649")
                actions = [button.action for button in response.outbound.buttons]

                self.assertIn(f"Роль в боте: {display_role_name(role.value)}", response.outbound.text)
                self.assertIn(BotAction.MAIN_MENU, actions)
                if role == Role.ADMIN:
                    self.assertIn(BotAction.MENU_ADMIN_PANEL, actions)
                else:
                    self.assertNotIn(BotAction.MENU_ADMIN_PANEL, actions)


if __name__ == "__main__":
    unittest.main()
