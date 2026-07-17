from __future__ import annotations

import unittest

from app.integrations.google_sheets.directory import GoogleSheetsEmployeeRecord
from app.bot.router import MaxWebhookRouter
from app.services.role_resolver import RoleResolver


class _FakeGoogleDirectoryService:
    def __init__(self, record=None):
        self.record = record
        self.refresh_calls = []

    def get_by_user_id(self, user_id: str, refresh: bool = False):
        self.refresh_calls.append(refresh)
        return self.record


class _FakeRoleOverrideRepository:
    def __init__(self, role: str | None = None):
        self.role = role

    def get_role(self, user_id: str):
        return self.role


class _FakeEmployeeDirectoryRepository:
    def __init__(self, role: str | None = None):
        self.role = role
        self.calls = 0

    def get_by_user_id(self, user_id: str):
        self.calls += 1
        if self.role is None:
            return None
        return type("Row", (), {"role": self.role, "is_active": True})()


class RoleResolverTests(unittest.TestCase):
    def test_router_reuses_directory_dependencies_for_role_resolver(self) -> None:
        router = MaxWebhookRouter()

        self.assertIs(router.role_resolver.google_directory_service, router.google_directory_service)
        self.assertIs(router.role_resolver.employee_directory_repository, router.employee_directory_repository)
        self.assertIs(router.role_resolver.role_override_repository, router.user_role_override_repository)

    def test_override_takes_priority_over_local_directory(self) -> None:
        employee_repository = _FakeEmployeeDirectoryRepository("manager")
        resolver = RoleResolver(
            google_directory_service=_FakeGoogleDirectoryService(
                GoogleSheetsEmployeeRecord(
                    employee_name="Иванов Иван Иванович",
                    employee_user_id="max_001",
                    role="Администратор",
                    is_active=True,
                )
            ),
            role_override_repository=_FakeRoleOverrideRepository("employee"),
            employee_directory_repository=employee_repository,
        )

        self.assertEqual(resolver.resolve_role("max_001", "private"), "employee")
        self.assertEqual(resolver.resolve_role("max_001", "private"), "employee")
        self.assertEqual(employee_repository.calls, 0)
        self.assertEqual(resolver.google_directory_service.refresh_calls, [])

    def test_override_is_used_when_directory_has_different_role(self) -> None:
        resolver = RoleResolver(
            google_directory_service=_FakeGoogleDirectoryService(None),
            role_override_repository=_FakeRoleOverrideRepository("manager"),
            employee_directory_repository=_FakeEmployeeDirectoryRepository("employee"),
        )

        self.assertEqual(resolver.resolve_role("max_002", "private"), "manager")
        self.assertEqual(resolver.google_directory_service.refresh_calls, [])

    def test_google_sheet_is_used_when_local_cache_is_empty(self) -> None:
        resolver = RoleResolver(
            google_directory_service=_FakeGoogleDirectoryService(
                GoogleSheetsEmployeeRecord(
                    employee_user_id="max_003",
                    role="Администратор",
                    is_active=True,
                )
            ),
            role_override_repository=_FakeRoleOverrideRepository(None),
            employee_directory_repository=_FakeEmployeeDirectoryRepository(None),
        )

        self.assertEqual(resolver.resolve_role("max_003", "private"), "admin")
        self.assertEqual(resolver.google_directory_service.refresh_calls, [False])

    def test_google_sheet_role_takes_priority_over_stale_local_directory(self) -> None:
        resolver = RoleResolver(
            google_directory_service=_FakeGoogleDirectoryService(
                GoogleSheetsEmployeeRecord(
                    employee_user_id="max_004",
                    role="top_manager",
                    is_active=True,
                )
            ),
            role_override_repository=_FakeRoleOverrideRepository(None),
            employee_directory_repository=_FakeEmployeeDirectoryRepository("manager"),
        )

        self.assertEqual(resolver.resolve_role("max_004", "private"), "top_manager")

    def test_local_directory_is_used_when_google_sheet_has_no_active_record(self) -> None:
        resolver = RoleResolver(
            google_directory_service=_FakeGoogleDirectoryService(None),
            role_override_repository=_FakeRoleOverrideRepository(None),
            employee_directory_repository=_FakeEmployeeDirectoryRepository("manager"),
        )

        self.assertEqual(resolver.resolve_role("max_005", "private"), "manager")


if __name__ == "__main__":
    unittest.main()
