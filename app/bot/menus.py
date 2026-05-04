from __future__ import annotations

from typing import Dict, List

from app.bot.buttons import main_menu_buttons

ROLE_MENUS: Dict[str, List[str]] = {
    "employee": [button.title for button in main_menu_buttons("employee")],
    "manager": [button.title for button in main_menu_buttons("manager")],
    "security": [button.title for button in main_menu_buttons("security")],
    "hr": [button.title for button in main_menu_buttons("hr")],
    "admin": [button.title for button in main_menu_buttons("admin")],
    "top_manager": [button.title for button in main_menu_buttons("top_manager")],
}


def get_menu_for_role(role: str) -> List[str]:
    return ROLE_MENUS.get(role, ROLE_MENUS["employee"])
