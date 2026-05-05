from __future__ import annotations

import unittest

from app.bot.router import MaxWebhookRouter


class _FakeGoogleDirectoryService:
    def get_by_user_id(self, user_id: str, refresh: bool = False):
        return None


class AdminPanelMenuTests(unittest.TestCase):
    def test_admin_panel_mentions_google_sheets_status(self) -> None:
        router = MaxWebhookRouter()
        router.google_directory_service = _FakeGoogleDirectoryService()

        response = router._admin_panel_menu("admin", "203302812")

        self.assertIn("Админ-панель", response.outbound.text)
        self.assertIn("Текущая роль: Администратор", response.outbound.text)
        self.assertIn("Google Sheets", response.outbound.text)
        self.assertIn("Права доступа", [button.title for button in response.outbound.buttons])


if __name__ == "__main__":
    unittest.main()
