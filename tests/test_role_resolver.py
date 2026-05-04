from __future__ import annotations

import unittest

from app.integrations.google_sheets.directory import GoogleSheetsEmployeeRecord
from app.services.role_resolver import RoleResolver


class _FakeGoogleDirectoryService:
    def __init__(self, record=None):
        self.record = record

    def get_by_user_id(self, user_id: str, refresh: bool = False):
        return self.record


class _FakeRoleOverrideRepository:
    def __init__(self, role: str | None = None):
        self.role = role

    def get_role(self, user_id: str):
        return self.role


class _FakeEmployeeDirectoryRepository:
    def __init__(self, role: str | None = None):
        self.role = role

    def get_by_user_id(self, user_id: str):
        if self.role is None:
            return None
        return type("Row", (), {"role": self.role, "is_active": True})()


class RoleResolverTests(unittest.TestCase):
    def test_google_sheet_role_takes_priority_and_normalizes(self) -> None:
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
            employee_directory_repository=_FakeEmployeeDirectoryRepository("manager"),
        )

        self.assertEqual(resolver.resolve_role("max_001", "private"), "admin")

    def test_override_is_used_when_sheet_is_empty(self) -> None:
        resolver = RoleResolver(
            google_directory_service=_FakeGoogleDirectoryService(None),
            role_override_repository=_FakeRoleOverrideRepository("manager"),
            employee_directory_repository=_FakeEmployeeDirectoryRepository("employee"),
        )

        self.assertEqual(resolver.resolve_role("max_002", "private"), "manager")


if __name__ == "__main__":
    unittest.main()
