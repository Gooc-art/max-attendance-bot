from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from docx_leadership_sync import (
    EmployeeSheetRow,
    build_employee_index,
    build_employee_updates,
    build_normalized_rows,
    parse_template_rows,
)


class DocxLeadershipSyncTests(unittest.TestCase):
    def test_parse_template_rows_uses_expected_columns(self) -> None:
        values = [
            [
                "№",
                "ФИО",
                "Подразделение",
                "ФИО_руководителя",
                "ФИО_замещающего",
                "ФИО_топ_руководителя",
                "Комментарий",
            ],
            [
                "1",
                "Иванов Иван Иванович",
                "Отдел продаж",
                "Петров Петр Сергеевич",
                "Сидоров Сидор Сидорович",
                "Орлов Олег Олегович",
                "Проверка",
            ],
        ]

        rows = parse_template_rows(values)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.employee_name, "Иванов Иван Иванович")
        self.assertEqual(row.department_name, "Отдел продаж")
        self.assertEqual(row.manager_name, "Петров Петр Сергеевич")
        self.assertEqual(row.replacement_name, "Сидоров Сидор Сидорович")
        self.assertEqual(row.top_manager_name, "Орлов Олег Олегович")
        self.assertEqual(row.comment, "Проверка")

    def test_build_employee_updates_uses_employee_sheet_rows(self) -> None:
        rows = parse_template_rows(
            [
                ["№", "ФИО", "Подразделение", "ФИО_руководителя", "ФИО_замещающего", "ФИО_топ_руководителя", "Комментарий"],
                ["1", "Иванов Иван Иванович", "Отдел продаж", "Петров Петр Сергеевич", "", "", ""],
            ]
        )
        employee_index = {
            "Иванов Иван Иванович": EmployeeSheetRow(row_number=2, employee_name="Иванов Иван Иванович", employee_user_id="max_001")
        }

        updates = build_employee_updates(rows, employee_index)

        self.assertEqual(
            [(item.row_number, item.column, item.value) for item in updates],
            [(2, "G", "Отдел продаж"), (2, "E", "Петров Петр Сергеевич")],
        )

    def test_build_normalized_rows_marks_missing_manager(self) -> None:
        rows = parse_template_rows(
            [
                ["№", "ФИО", "Подразделение", "ФИО_руководителя", "ФИО_замещающего", "ФИО_топ_руководителя", "Комментарий"],
                ["1", "Иванов Иван Иванович", "", "", "", "", ""],
            ]
        )
        employee_index = build_employee_index(
            [
                ["ФИО", "ID_пользователя_MAX"],
                ["Иванов Иван Иванович", "max_001"],
            ]
        )

        normalized = build_normalized_rows(rows, employee_index)

        self.assertEqual(normalized[0][1], "Иванов Иван Иванович")
        self.assertEqual(normalized[0][2], "max_001")
        self.assertEqual(normalized[0][9], "Ожидает заполнения руководителя")


if __name__ == "__main__":
    unittest.main()
