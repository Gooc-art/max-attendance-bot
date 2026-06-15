from __future__ import annotations

import unittest

from app.bot.actions import BotAction
from app.bot.buttons import main_menu_buttons


class AdminButtonsTests(unittest.TestCase):
    def test_admin_menu_starts_with_start_button(self) -> None:
        buttons = main_menu_buttons("admin")
        self.assertEqual(buttons[0].title, "Старт")
        self.assertEqual(buttons[0].action, BotAction.START)

    def test_admin_menu_shows_whoami_button_second(self) -> None:
        buttons = main_menu_buttons("admin")
        self.assertEqual(buttons[1].title, "Обо мне")
        self.assertEqual(buttons[1].action, BotAction.WHOAMI)

    def test_admin_menu_shows_admin_panel_button_third(self) -> None:
        buttons = main_menu_buttons("admin")
        self.assertGreater(len(buttons), 3)
        self.assertEqual(buttons[2].title, "Админ-панель")
        self.assertEqual(buttons[2].action, BotAction.MENU_ADMIN_PANEL)

    def test_admin_menu_shows_access_rights_button_fourth(self) -> None:
        buttons = main_menu_buttons("admin")
        self.assertGreater(len(buttons), 4)
        self.assertEqual(buttons[3].title, "Права доступа")
        self.assertEqual(buttons[3].action, BotAction.MENU_ACCESS_RIGHTS)

    def test_admin_menu_shows_personal_section_fifth(self) -> None:
        buttons = main_menu_buttons("admin")
        self.assertGreater(len(buttons), 5)
        self.assertEqual(buttons[4].title, "Личное")
        self.assertEqual(buttons[4].action, BotAction.ADMIN_PERSONAL)

    def test_admin_menu_shows_structure_section(self) -> None:
        buttons = main_menu_buttons("admin")
        self.assertIn("Структура", [button.title for button in buttons])
        self.assertIn(BotAction.ADMIN_STRUCTURE, [button.action for button in buttons])

    def test_admin_menu_shows_report_block_section(self) -> None:
        buttons = main_menu_buttons("admin")
        self.assertIn("Отчетный блок", [button.title for button in buttons])
        self.assertIn(BotAction.ADMIN_REPORTS, [button.action for button in buttons])


if __name__ == "__main__":
    unittest.main()
