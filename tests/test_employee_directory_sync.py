from __future__ import annotations

import unittest

from app.integrations.google_sheets.directory import GoogleSheetsEmployeeRecord
from app.services.employee_directory_sync import EmployeeDirectorySyncService


class _DirectoryService:
    def __init__(self, records, configured: bool = True) -> None:
        self.records = records
        self.configured = configured
        self.refresh_calls = []

    def is_configured(self) -> bool:
        return self.configured

    def list_employees(self, refresh: bool = False):
        self.refresh_calls.append(refresh)
        return list(self.records)


class _Repository:
    def __init__(self) -> None:
        self.rows = []

    def upsert_many(self, rows):
        self.rows = list(rows)
        return len(self.rows)


class EmployeeDirectorySyncTests(unittest.TestCase):
    def test_sync_upserts_google_records_with_schedule_fields(self) -> None:
        repository = _Repository()
        directory = _DirectoryService(
            [
                GoogleSheetsEmployeeRecord(
                    employee_name="Иванов Иван Иванович",
                    employee_user_id="max-1",
                    manager_name="Петров Петр Петрович",
                    manager_user_id="max-2",
                    department_name="ИТ",
                    office="314",
                    schedule_name="Пятидневка",
                    schedule_id="ГР004",
                    role="manager",
                    is_active=True,
                )
            ]
        )

        result = EmployeeDirectorySyncService(directory_service=directory, repository=repository).sync()

        self.assertTrue(result.configured)
        self.assertEqual(result.fetched_rows, 1)
        self.assertEqual(result.upserted_rows, 1)
        self.assertEqual(repository.rows[0]["schedule_id"], "ГР004")
        self.assertEqual(repository.rows[0]["office"], "314")
        self.assertEqual(directory.refresh_calls, [True])

    def test_sync_uses_manager_name_from_manager_user_id(self) -> None:
        repository = _Repository()
        directory = _DirectoryService(
            [
                GoogleSheetsEmployeeRecord(
                    employee_name="Иванов Иван Иванович",
                    employee_user_id="max-1",
                    manager_name="Старое Имя Руководителя",
                    manager_user_id="max-2",
                    department_name="ИТ",
                    role="employee",
                    is_active=True,
                ),
                GoogleSheetsEmployeeRecord(
                    employee_name="Петров Петр Петрович",
                    employee_user_id="max-2",
                    department_name="ИТ",
                    role="зам.руководителя",
                    is_active=True,
                ),
            ]
        )

        EmployeeDirectorySyncService(directory_service=directory, repository=repository).sync()

        self.assertEqual(repository.rows[0]["manager_name"], "Петров Петр Петрович")
        self.assertEqual(repository.rows[1]["role"], "manager")

    def test_sync_skips_when_google_is_not_configured(self) -> None:
        repository = _Repository()
        result = EmployeeDirectorySyncService(
            directory_service=_DirectoryService([], configured=False),
            repository=repository,
        ).sync()

        self.assertFalse(result.configured)
        self.assertEqual(repository.rows, [])


if __name__ == "__main__":
    unittest.main()
