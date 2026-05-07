from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.integrations.google_sheets.directory import GoogleSheetsDirectoryService


class _FakeGoogleSheetsDirectoryService(GoogleSheetsDirectoryService):
    def __init__(self, values):
        super().__init__(spreadsheet_id="sheet-id", service_account_file=__file__, employee_range="Сотрудники!A:Q")
        self._values = values

    def is_configured(self) -> bool:
        return True

    def _fetch_values(self):
        return self._values


class GoogleSheetsDirectoryServiceTests(unittest.TestCase):
    def test_parse_values_maps_columns_and_normalizes_roles(self) -> None:
        service = _FakeGoogleSheetsDirectoryService(
            [
                [
                    "ФИО",
                    "ID_пользователя_MAX",
                    "ФИО_руководителя",
                    "ID_руководителя_MAX",
                    "Подразделение",
                    "Роль",
                    "Работает",
                ],
                [
                    "Иванов Иван Иванович",
                    "max_001",
                    "Петров Петр Сергеевич",
                    "max_002",
                    "Отдел продаж",
                    "Администратор",
                    "Да",
                ],
            ]
        )

        records = service.list_employees(refresh=True)

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.employee_name, "Иванов Иван Иванович")
        self.assertEqual(record.employee_user_id, "max_001")
        self.assertEqual(record.manager_name, "Петров Петр Сергеевич")
        self.assertEqual(record.manager_user_id, "max_002")
        self.assertEqual(record.department_name, "Отдел продаж")
        self.assertEqual(record.role, "admin")
        self.assertTrue(record.is_active)

    def test_list_employees_uses_cached_records_when_fetch_fails(self) -> None:
        service = _FakeGoogleSheetsDirectoryService(
            [
                ["ФИО", "ID_пользователя_MAX", "Роль", "Работает"],
                ["Иванов Иван Иванович", "max_001", "Администратор", "Да"],
            ]
        )

        first_pass = service.list_employees(refresh=True)
        self.assertEqual(len(first_pass), 1)

        service._cached_at = datetime.now(timezone.utc) - timedelta(seconds=600)

        def _raise():
            raise RuntimeError("quota exceeded")

        service._fetch_values = _raise  # type: ignore[method-assign]

        cached = service.list_employees(refresh=False)
        self.assertEqual(len(cached), 1)
        self.assertEqual(cached[0].employee_user_id, "max_001")


if __name__ == "__main__":
    unittest.main()
