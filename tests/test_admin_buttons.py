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
        self.assertEqual(buttons[1].title, "Кто я")
        self.assertEqual(buttons[1].action, BotAction.WHOAMI)

    def test_admin_menu_shows_my_row_button_third(self) -> None:
        buttons = main_menu_buttons("admin")
        self.assertGreater(len(buttons), 3)
        self.assertEqual(buttons[2].title, "Моя строка")
        self.assertEqual(buttons[2].action, BotAction.MENU_MY_ROW)

    def test_admin_menu_shows_binding_check_button_fourth(self) -> None:
        buttons = main_menu_buttons("admin")
        self.assertGreater(len(buttons), 4)
        self.assertEqual(buttons[3].title, "Проверить привязку")
        self.assertEqual(buttons[3].action, BotAction.MENU_BINDING_CHECK)

    def test_admin_menu_promotes_admin_panel_button(self) -> None:
        buttons = main_menu_buttons("admin")
        self.assertGreater(len(buttons), 4)
        self.assertEqual(buttons[4].title, "Админ-панель")
        self.assertEqual(buttons[4].action, BotAction.MENU_ADMIN_PANEL)


if __name__ == "__main__":
    unittest.main()
