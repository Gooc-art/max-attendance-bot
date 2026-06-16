from __future__ import annotations

ROLE_DISPLAY_NAMES = {
    "employee": "Сотрудник",
    "manager": "Начальник отдела",
    "security": "Служба безопасности",
    "hr": "HR",
    "admin": "Администратор",
    "top_manager": "Главный руководитель",
}


def display_role_name(role: str) -> str:
    normalized = str(role or "").strip()
    return ROLE_DISPLAY_NAMES.get(normalized, normalized or "Сотрудник")
