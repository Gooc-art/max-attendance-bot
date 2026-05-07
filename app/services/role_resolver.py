from __future__ import annotations

from app.integrations.google_sheets.directory import GoogleSheetsDirectoryService
from app.repositories.user_role_override_repository import UserRoleOverrideRepository
from app.repositories.employee_directory_repository import EmployeeDirectoryRepository


class RoleResolver:
    """Resolve MAX user role using overrides, employee directory, and known prefixes."""

    SECURITY_PREFIX = "sec_"
    HR_PREFIX = "hr_"
    ADMIN_PREFIX = "admin_"
    TOP_MANAGER_PREFIX = "top_"
    MANAGER_PREFIX = "mgr_"

    def __init__(
        self,
        google_directory_service: GoogleSheetsDirectoryService | None = None,
        role_override_repository: UserRoleOverrideRepository | None = None,
        employee_directory_repository: EmployeeDirectoryRepository | None = None,
    ) -> None:
        self.google_directory_service = google_directory_service or GoogleSheetsDirectoryService.from_settings()
        self.role_override_repository = UserRoleOverrideRepository()
        if role_override_repository is not None:
            self.role_override_repository = role_override_repository
        self.employee_directory_repository = employee_directory_repository or EmployeeDirectoryRepository()

    def resolve_role(self, user_id: str, chat_id: str) -> str:
        sheet_record = self.google_directory_service.get_by_user_id(user_id, refresh=True)
        if sheet_record is not None and sheet_record.is_active and sheet_record.role:
            return self._normalize_role(sheet_record.role)
        override_role = self.role_override_repository.get_role(user_id)
        if override_role:
            return self._normalize_role(override_role)
        record = self.employee_directory_repository.get_by_user_id(user_id)
        if record is not None and record.is_active:
            if record.role:
                return self._normalize_role(record.role)
            return "employee"
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

    @staticmethod
    def _normalize_role(role: str) -> str:
        return GoogleSheetsDirectoryService.normalize_role_value(role)
