from __future__ import annotations

import logging
from time import perf_counter
from time import monotonic

from app.integrations.google_sheets.directory import GoogleSheetsDirectoryService
from app.repositories.user_role_override_repository import UserRoleOverrideRepository
from app.repositories.employee_directory_repository import EmployeeDirectoryRepository


logger = logging.getLogger(__name__)


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
        self._cache_ttl_seconds = 300
        self._role_cache: dict[str, tuple[float, str]] = {}

    def resolve_role(self, user_id: str, chat_id: str) -> str:
        started_at = perf_counter()
        cached_role = self._cached_role(user_id)
        if cached_role:
            logger.info("Role resolved user_id=%s chat_id=%s role=%s source=%s elapsed_ms=%.1f", user_id, chat_id, cached_role, "memory_cache", (perf_counter() - started_at) * 1000)
            return cached_role

        override_role = self.role_override_repository.get_role(user_id)
        if override_role:
            source = "override"
            resolved_role = self._normalize_role(override_role)
            self._remember_role(user_id, resolved_role)
            logger.info("Role resolved user_id=%s chat_id=%s role=%s source=%s elapsed_ms=%.1f", user_id, chat_id, resolved_role, source, (perf_counter() - started_at) * 1000)
            return resolved_role
        record = self.employee_directory_repository.get_by_user_id(user_id)
        if record is not None and record.is_active:
            if record.role:
                source = "employee_directory_role"
                resolved_role = self._normalize_role(record.role)
                self._remember_role(user_id, resolved_role)
                logger.info("Role resolved user_id=%s chat_id=%s role=%s source=%s elapsed_ms=%.1f", user_id, chat_id, resolved_role, source, (perf_counter() - started_at) * 1000)
                return resolved_role
            source = "employee_directory_default"
            self._remember_role(user_id, "employee")
            logger.info("Role resolved user_id=%s chat_id=%s role=%s source=%s elapsed_ms=%.1f", user_id, chat_id, "employee", source, (perf_counter() - started_at) * 1000)
            return "employee"
        source = "default"
        sheet_record = self.google_directory_service.get_by_user_id(user_id)
        if sheet_record is not None and sheet_record.is_active and sheet_record.role:
            source = "google_sheets"
            resolved_role = self._normalize_role(sheet_record.role)
            self._remember_role(user_id, resolved_role)
            logger.info("Role resolved user_id=%s chat_id=%s role=%s source=%s elapsed_ms=%.1f", user_id, chat_id, resolved_role, source, (perf_counter() - started_at) * 1000)
            return resolved_role
        if user_id.startswith(self.SECURITY_PREFIX):
            source = "security_prefix"
            self._remember_role(user_id, "security")
            logger.info("Role resolved user_id=%s chat_id=%s role=%s source=%s elapsed_ms=%.1f", user_id, chat_id, "security", source, (perf_counter() - started_at) * 1000)
            return "security"
        if user_id.startswith(self.HR_PREFIX):
            source = "hr_prefix"
            self._remember_role(user_id, "hr")
            logger.info("Role resolved user_id=%s chat_id=%s role=%s source=%s elapsed_ms=%.1f", user_id, chat_id, "hr", source, (perf_counter() - started_at) * 1000)
            return "hr"
        if user_id.startswith(self.ADMIN_PREFIX):
            source = "admin_prefix"
            self._remember_role(user_id, "admin")
            logger.info("Role resolved user_id=%s chat_id=%s role=%s source=%s elapsed_ms=%.1f", user_id, chat_id, "admin", source, (perf_counter() - started_at) * 1000)
            return "admin"
        if user_id.startswith(self.TOP_MANAGER_PREFIX):
            source = "top_manager_prefix"
            self._remember_role(user_id, "top_manager")
            logger.info("Role resolved user_id=%s chat_id=%s role=%s source=%s elapsed_ms=%.1f", user_id, chat_id, "top_manager", source, (perf_counter() - started_at) * 1000)
            return "top_manager"
        if user_id.startswith(self.MANAGER_PREFIX):
            source = "manager_prefix"
            self._remember_role(user_id, "manager")
            logger.info("Role resolved user_id=%s chat_id=%s role=%s source=%s elapsed_ms=%.1f", user_id, chat_id, "manager", source, (perf_counter() - started_at) * 1000)
            return "manager"
        if chat_id.startswith("group_security"):
            source = "group_security_prefix"
            self._remember_role(user_id, "security")
            logger.info("Role resolved user_id=%s chat_id=%s role=%s source=%s elapsed_ms=%.1f", user_id, chat_id, "security", source, (perf_counter() - started_at) * 1000)
            return "security"
        self._remember_role(user_id, "employee")
        logger.info("Role resolved user_id=%s chat_id=%s role=%s source=%s elapsed_ms=%.1f", user_id, chat_id, "employee", source, (perf_counter() - started_at) * 1000)
        return "employee"

    def clear_user_cache(self, user_id: str) -> None:
        self._role_cache.pop(str(user_id or "").strip(), None)

    def _cached_role(self, user_id: str) -> str:
        key = str(user_id or "").strip()
        if not key:
            return ""
        cached = self._role_cache.get(key)
        if not cached:
            return ""
        expires_at, role = cached
        if expires_at <= monotonic():
            self._role_cache.pop(key, None)
            return ""
        return role

    def _remember_role(self, user_id: str, role: str) -> None:
        key = str(user_id or "").strip()
        if key and role:
            self._role_cache[key] = (monotonic() + self._cache_ttl_seconds, role)

    @staticmethod
    def _normalize_role(role: str) -> str:
        return GoogleSheetsDirectoryService.normalize_role_value(role)
