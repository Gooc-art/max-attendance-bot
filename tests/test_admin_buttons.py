from __future__ import annotations

import unittest

from app.bot.actions import BotAction
from app.bot.buttons import main_menu_buttons


class AdminButtonsTests(unittest.TestCase):
    def test_admin_menu_starts_with_whoami_button(self) -> None:
        buttons = main_menu_buttons("admin")
        self.assertEqual(buttons[0].title, "Обо мне")
        self.assertEqual(buttons[0].action, BotAction.WHOAMI)

    def test_admin_menu_shows_personal_section_second(self) -> None:
        buttons = main_menu_buttons("admin")
        self.assertEqual(buttons[1].title, "Личное")
        self.assertEqual(buttons[1].action, BotAction.ADMIN_PERSONAL)

    def test_admin_menu_shows_structure_section_third(self) -> None:
        buttons = main_menu_buttons("admin")
        self.assertGreater(len(buttons), 3)
        self.assertEqual(buttons[2].title, "Структура")
        self.assertEqual(buttons[2].action, BotAction.ADMIN_STRUCTURE)

    def test_admin_menu_shows_skud_section_fourth(self) -> None:
        buttons = main_menu_buttons("admin")
        self.assertGreater(len(buttons), 4)
        self.assertEqual(buttons[3].title, "СКУД")
        self.assertEqual(buttons[3].action, BotAction.ADMIN_SKUD)

    def test_admin_menu_shows_workflow_section_fifth(self) -> None:
        buttons = main_menu_buttons("admin")
        self.assertGreater(len(buttons), 5)
        self.assertEqual(buttons[4].title, "Процессы")
        self.assertEqual(buttons[4].action, BotAction.ADMIN_WORKFLOW)

    def test_admin_menu_does_not_show_diagnostics_as_top_level_buttons(self) -> None:
        titles = [button.title for button in main_menu_buttons("admin")]
        actions = [button.action for button in main_menu_buttons("admin")]

        self.assertNotIn("Старт", titles)
        self.assertNotIn(BotAction.START, actions)
        self.assertNotIn("Админ-панель", titles)
        self.assertNotIn(BotAction.MENU_ADMIN_PANEL, actions)
        self.assertNotIn("Права доступа", titles)
        self.assertNotIn(BotAction.MENU_ACCESS_RIGHTS, actions)

    def test_admin_menu_shows_structure_section(self) -> None:
        buttons = main_menu_buttons("admin")
        self.assertIn("Структура", [button.title for button in buttons])
        self.assertIn(BotAction.ADMIN_STRUCTURE, [button.action for button in buttons])

    def test_admin_menu_shows_report_block_section(self) -> None:
        buttons = main_menu_buttons("admin")
        self.assertIn("Отчеты", [button.title for button in buttons])
        self.assertIn(BotAction.ADMIN_REPORTS, [button.action for button in buttons])


if __name__ == "__main__":
    unittest.main()
