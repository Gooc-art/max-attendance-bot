from __future__ import annotations

import re
import unittest
from pathlib import Path

from app.bot.actions import BotAction
from app.bot.buttons import (
    admin_reports_buttons,
    admin_skud_buttons,
    admin_structure_buttons,
    admin_workflow_buttons,
    approvals_menu_buttons,
    employee_manager_section_buttons,
    employee_personal_buttons,
    employee_reason_section_buttons,
    hr_reference_buttons,
    hr_reports_buttons,
    hr_workflow_buttons,
    main_menu_buttons,
    manager_management_buttons,
    reports_menu_buttons,
    security_skud_buttons,
    substitutions_menu_buttons,
    top_reports_buttons,
    top_summary_buttons,
)


ROOT = Path(__file__).resolve().parents[1]
HIDDEN_STUB_ACTIONS = {
    BotAction.SECURITY_AUDIT,
    BotAction.MENU_MATCH_ERRORS,
    BotAction.MENU_UNPROCESSED,
    BotAction.HR_SETTINGS,
    BotAction.MENU_SCHEDULES,
    BotAction.MENU_EXCEPTIONS,
    BotAction.MENU_SETTINGS,
    BotAction.ADMIN_SETTINGS,
}


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

    def test_visible_menus_do_not_link_to_hidden_stub_actions(self) -> None:
        menus = [
            *(main_menu_buttons(role) for role in ["employee", "manager", "security", "hr", "admin", "top_manager"]),
            employee_personal_buttons(),
            employee_reason_section_buttons(),
            employee_manager_section_buttons(),
            manager_management_buttons(),
            security_skud_buttons(),
            hr_reference_buttons(),
            hr_workflow_buttons(),
            hr_reports_buttons(),
            top_summary_buttons(),
            top_reports_buttons(),
            admin_structure_buttons(),
            admin_skud_buttons(),
            admin_workflow_buttons(),
            admin_reports_buttons(),
            approvals_menu_buttons(),
            reports_menu_buttons(),
            substitutions_menu_buttons(),
        ]
        actions = [button.action for buttons in menus for button in buttons]

        self.assertEqual(sorted(set(actions) & HIDDEN_STUB_ACTIONS), [])


if __name__ == "__main__":
    unittest.main()
