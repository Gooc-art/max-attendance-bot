from __future__ import annotations

from app.repositories.user_role_override_repository import UserRoleOverrideRepository


class RoleResolver:
    """Temporary role resolver before employee directory is connected."""

    SECURITY_PREFIX = "sec_"
    HR_PREFIX = "hr_"
    ADMIN_PREFIX = "admin_"
    TOP_MANAGER_PREFIX = "top_"
    MANAGER_PREFIX = "mgr_"

    def __init__(self) -> None:
        self.role_override_repository = UserRoleOverrideRepository()

    def resolve_role(self, user_id: str, chat_id: str) -> str:
        override_role = self.role_override_repository.get_role(user_id)
        if override_role:
            return override_role
        if user_id.startswith(self.SECURITY_PREFIX):
            return "security"
        if user_id.startswith(self.HR_PREFIX):
            return "hr"
        if user_id.startswith(self.ADMIN_PREFIX):
            return "admin"
        if user_id.startswith(self.TOP_MANAGER_PREFIX):
            return "top_manager"
        if user_id.startswith(self.MANAGER_PREFIX):
            return "manager"
        if chat_id.startswith("group_security"):
            return "security"
        return "employee"
