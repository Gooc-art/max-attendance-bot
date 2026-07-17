from __future__ import annotations

import unittest

from app.bot.router import MaxWebhookRouter


class AdminSectionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = MaxWebhookRouter()

    def test_admin_personal_section_is_compact(self) -> None:
        response = self.router._admin_personal_menu("admin")
        titles = [button.title for button in response.outbound.buttons]

        self.assertIn("Обо мне", titles)
        self.assertIn("Моя строка", titles)
        self.assertIn("Права доступа", titles)
        self.assertIn("Главное меню", titles)

    def test_admin_structure_section_contains_hr_shortcuts(self) -> None:
        response = self.router._admin_structure_menu("admin")
        titles = [button.title for button in response.outbound.buttons]

        self.assertIn("Сотрудники", titles)
        self.assertIn("Подразделения", titles)
        self.assertNotIn("Графики", titles)
        self.assertNotIn("Исключения", titles)

    def test_admin_skud_section_contains_import_shortcuts(self) -> None:
        response = self.router._admin_skud_menu("admin")
        titles = [button.title for button in response.outbound.buttons]

        self.assertIn("Импорт СКУД", titles)
        self.assertIn("История", titles)
        self.assertNotIn("Ошибки", titles)
        self.assertNotIn("Необработанные", titles)

    def test_admin_workflow_section_contains_approval_shortcuts(self) -> None:
        response = self.router._admin_workflow_menu("admin")
        titles = [button.title for button in response.outbound.buttons]

        self.assertIn("Согласования", titles)
        self.assertIn("Нарушения", titles)
        self.assertIn("Замещения", titles)

    def test_admin_reports_section_contains_report_shortcuts(self) -> None:
        response = self.router._admin_reports_menu("admin")
        titles = [button.title for button in response.outbound.buttons]

        self.assertIn("Сводка", titles)
        self.assertIn("Отчеты", titles)
        self.assertIn("По отделам", titles)


if __name__ == "__main__":
    unittest.main()
