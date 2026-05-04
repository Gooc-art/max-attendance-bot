from __future__ import annotations

import unittest

from app.bot.actions import BotAction
from app.bot.buttons import main_menu_buttons


class AdminButtonsTests(unittest.TestCase):
    def test_admin_menu_starts_with_start_button(self) -> None:
        buttons = main_menu_buttons("admin")
        self.assertEqual(buttons[0].title, "Старт")
        self.assertEqual(buttons[0].action, BotAction.START)

    def test_admin_menu_promotes_access_rights_button(self) -> None:
        buttons = main_menu_buttons("admin")
        self.assertGreater(len(buttons), 1)
        self.assertEqual(buttons[1].title, "Права доступа")
        self.assertEqual(buttons[1].action, BotAction.MENU_ACCESS_RIGHTS)


if __name__ == "__main__":
    unittest.main()
