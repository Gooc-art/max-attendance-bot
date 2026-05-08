from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ButtonActionMapTests(unittest.TestCase):
    def test_every_button_action_has_a_router_branch(self) -> None:
        buttons_src = (ROOT / "app" / "bot" / "buttons.py").read_text()
        router_src = (ROOT / "app" / "bot" / "router.py").read_text()

        button_actions = sorted(set(re.findall(r"BotAction\\.([A-Z_]+)", buttons_src)))
        router_actions = set(re.findall(r"BotAction\\.([A-Z_]+)", router_src))

        missing = [action for action in button_actions if action not in router_actions and action not in {"CANCEL", "CONFIRM"}]

        self.assertEqual(
            missing,
            [],
            msg=f"Missing router branches for button actions: {', '.join(missing)}",
        )


if __name__ == "__main__":
    unittest.main()
