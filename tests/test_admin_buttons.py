from __future__ import annotations

import unittest

from app.bot.actions import BotAction
from app.bot.buttons import main_menu_buttons


class AdminButtonsTests(unittest.TestCase):
    def test_admin_menu_starts_with_whoami_button(self) -> None:
        buttons = main_menu_buttons("admin")
        self.assertEqual(buttons[0].title, "Обо мне")
        self.assertEqual(buttons[0].action, BotAction.WHOAMI)

    def test_admin_menu_shows_running_late_section_second(self) -> None:
        buttons = main_menu_buttons("admin")
        self.assertEqual(buttons[1].title, "Опаздываю")
        self.assertEqual(buttons[1].action, BotAction.MENU_RUNNING_LATE)

    def test_admin_menu_shows_forgot_skud_card_section_third(self) -> None:
        buttons = main_menu_buttons("admin")
        self.assertGreater(len(buttons), 3)
        self.assertEqual(buttons[2].title, "Забыл карточку СКУД")
        self.assertEqual(buttons[2].action, BotAction.MENU_FORGOT_CHIP)

    def test_admin_menu_shows_personal_section(self) -> None:
        buttons = main_menu_buttons("admin")
        self.assertIn("Личное", [button.title for button in buttons])
        self.assertIn(BotAction.ADMIN_PERSONAL, [button.action for button in buttons])

    def test_admin_menu_shows_skud_section(self) -> None:
        buttons = main_menu_buttons("admin")
        self.assertIn("СКУД", [button.title for button in buttons])
        self.assertIn(BotAction.ADMIN_SKUD, [button.action for button in buttons])

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
