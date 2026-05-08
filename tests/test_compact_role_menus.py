from __future__ import annotations

import unittest

from app.bot.buttons import main_menu_buttons


class CompactRoleMenuTests(unittest.TestCase):
    def test_employee_menu_is_sectioned(self) -> None:
        titles = [button.title for button in main_menu_buttons("employee")]
        self.assertEqual(titles[:2], ["Старт", "Кто я"])
        self.assertIn("Личное", titles)
        self.assertIn("Причины", titles)
        self.assertIn("Руководство", titles)

    def test_manager_menu_is_sectioned(self) -> None:
        titles = [button.title for button in main_menu_buttons("manager")]
        self.assertEqual(titles[:2], ["Старт", "Кто я"])
        self.assertIn("Управление", titles)
        self.assertIn("Отчетный блок", titles)
        self.assertIn("Замещения", titles)
        self.assertIn("Процессы", titles)

    def test_security_menu_is_sectioned(self) -> None:
        titles = [button.title for button in main_menu_buttons("security")]
        self.assertEqual(titles[:2], ["Старт", "Кто я"])
        self.assertIn("СКУД", titles)
        self.assertIn("Журнал", titles)
        self.assertIn("Очередь", titles)

    def test_hr_menu_is_sectioned(self) -> None:
        titles = [button.title for button in main_menu_buttons("hr")]
        self.assertEqual(titles[:2], ["Старт", "Кто я"])
        self.assertIn("Справочники", titles)
        self.assertIn("Процессы", titles)
        self.assertIn("Отчетный блок", titles)
        self.assertIn("Параметры", titles)

    def test_top_menu_is_sectioned(self) -> None:
        titles = [button.title for button in main_menu_buttons("top_manager")]
        self.assertEqual(titles[:2], ["Старт", "Кто я"])
        self.assertIn("Аналитика", titles)
        self.assertIn("Отчетный блок", titles)
        self.assertIn("Процессы", titles)


if __name__ == "__main__":
    unittest.main()
