from __future__ import annotations

import unittest

from app.integrations.google_sheets.directory import GoogleSheetsEmployeeRecord
from app.services.employee_directory_sync import EmployeeDirectorySyncService


class _DirectoryService:
    def __init__(self, records, configured: bool = True, last_error=None) -> None:
        self.records = records
        self.configured = configured
        self.last_error = last_error
        self.refresh_calls = []

    def is_configured(self) -> bool:
        return self.configured

    def list_employees(self, refresh: bool = False):
        self.refresh_calls.append(refresh)
        return list(self.records)


class _Repository:
    def __init__(self) -> None:
        self.rows = []
        self.active_user_ids = set()
        self.deactivated_count = 0

    def upsert_many(self, rows):
        self.rows = list(rows)
        return len(self.rows)

    def deactivate_missing(self, active_user_ids):
        self.active_user_ids = set(active_user_ids)
        return self.deactivated_count


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
        self.assertEqual(result.deactivated_rows, 0)
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

    def test_sync_deactivates_local_rows_missing_from_successful_google_fetch(self) -> None:
        repository = _Repository()
        repository.deactivated_count = 2
        directory = _DirectoryService(
            [
                GoogleSheetsEmployeeRecord(
                    employee_name="Иванов Иван Иванович",
                    employee_user_id="max-1",
                    role="employee",
                    is_active=True,
                )
            ]
        )

        result = EmployeeDirectorySyncService(directory_service=directory, repository=repository).sync()

        self.assertEqual(repository.active_user_ids, {"max-1"})
        self.assertEqual(result.deactivated_rows, 2)

    def test_sync_rejects_duplicate_employee_user_id_without_writing(self) -> None:
        repository = _Repository()
        directory = _DirectoryService(
            [
                GoogleSheetsEmployeeRecord(employee_name="Первый", employee_user_id="max-1"),
                GoogleSheetsEmployeeRecord(employee_name="Второй", employee_user_id="max-1"),
            ]
        )

        with self.assertRaises(ValueError):
            EmployeeDirectorySyncService(directory_service=directory, repository=repository).sync()

        self.assertEqual(repository.rows, [])

    def test_sync_fails_when_google_fetch_failed(self) -> None:
        repository = _Repository()
        directory = _DirectoryService([], last_error=RuntimeError("google down"))

        with self.assertRaises(RuntimeError):
            EmployeeDirectorySyncService(directory_service=directory, repository=repository).sync()

        self.assertEqual(repository.rows, [])


if __name__ == "__main__":
    unittest.main()
