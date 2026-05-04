from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
