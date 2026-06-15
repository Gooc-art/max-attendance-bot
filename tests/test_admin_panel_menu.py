from __future__ import annotations

import unittest

from app.bot.router import MaxWebhookRouter


class _FakeGoogleDirectoryService:
    def __init__(self, configured: bool = True):
        self.configured = configured

    def get_by_user_id(self, user_id: str, refresh: bool = False):
        return None

    def is_configured(self) -> bool:
        return self.configured


class AdminPanelMenuTests(unittest.TestCase):
    def test_admin_panel_mentions_google_sheets_status(self) -> None:
        router = MaxWebhookRouter()
        router.google_directory_service = _FakeGoogleDirectoryService()

        response = router._admin_panel_menu("admin", "203302812")

        self.assertIn("Админ-панель", response.outbound.text)
        self.assertIn("Текущая роль: Администратор", response.outbound.text)
        self.assertIn("Google Sheets", response.outbound.text)
        self.assertIn("Личное", [button.title for button in response.outbound.buttons])
        self.assertIn("Структура", [button.title for button in response.outbound.buttons])
        self.assertIn("СКУД", [button.title for button in response.outbound.buttons])

    def test_admin_panel_reports_unconfigured_google_sheets_runtime(self) -> None:
        router = MaxWebhookRouter()
        router.google_directory_service = _FakeGoogleDirectoryService(configured=False)

        response = router._admin_panel_menu("admin", "203302812")

        self.assertIn("Google Sheets не настроен в текущей runtime-среде", response.outbound.text)


if __name__ == "__main__":
    unittest.main()
