from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from docx_leadership_sync import (
    EmployeeSheetRow,
    TOP_MANAGER_NAME,
    build_employee_index,
    build_employee_updates,
    build_normalized_rows,
    build_structure_index,
    parse_template_rows,
    resolve_manager_name,
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

        updates = build_employee_updates(rows, employee_index, {}, [])

        self.assertEqual(
            [(item.row_number, item.column, item.value) for item in updates],
            [(2, "G", "Отдел продаж"), (2, "E", "Петров Петр Сергеевич")],
        )

    def test_build_employee_updates_uses_structure_department_override(self) -> None:
        rows = parse_template_rows(
            [
                ["№", "ФИО", "Подразделение", "ФИО_руководителя", "ФИО_замещающего", "ФИО_топ_руководителя", "Комментарий"],
                ["1", "Антипина Луиза Николаевна", "", "", "", "", ""],
            ]
        )
        employee_index = {
            "Антипина Луиза Николаевна": EmployeeSheetRow(row_number=2, employee_name="Антипина Луиза Николаевна", employee_user_id="max_001")
        }

        updates = build_employee_updates(rows, employee_index, {"Антипина Луиза Николаевна": object()}, [])

        self.assertIn((2, "G", "8-ОРиУН"), [(item.row_number, item.column, item.value) for item in updates])

    def test_build_normalized_rows_marks_top_manager(self) -> None:
        rows = parse_template_rows(
            [
                ["№", "ФИО", "Подразделение", "ФИО_руководителя", "ФИО_замещающего", "ФИО_топ_руководителя", "Комментарий"],
                [f"1", TOP_MANAGER_NAME, "", "", "", "", ""],
            ]
        )
        employee_index = build_employee_index(
            [
                ["ФИО", "ID_пользователя_MAX"],
                [TOP_MANAGER_NAME, "max_001"],
            ]
        )

        normalized = build_normalized_rows(rows, employee_index, {}, [])

        self.assertEqual(normalized[0][1], TOP_MANAGER_NAME)
        self.assertEqual(normalized[0][2], "max_001")
        self.assertEqual(normalized[0][7], TOP_MANAGER_NAME)
        self.assertEqual(normalized[0][9], "Топ-уровень")

    def test_build_normalized_rows_uses_explicit_manager_override(self) -> None:
        rows = parse_template_rows(
            [
                ["№", "ФИО", "Подразделение", "ФИО_руководителя", "ФИО_замещающего", "ФИО_топ_руководителя", "Комментарий"],
                ["1", "Антипина Луиза Николаевна", "", "", "", "", ""],
            ]
        )
        employee_index = build_employee_index(
            [
                ["ФИО", "ID_пользователя_MAX"],
                ["Антипина Луиза Николаевна", "max_001"],
            ]
        )

        normalized = build_normalized_rows(rows, employee_index, {}, [])

        self.assertEqual(normalized[0][4], "Слабенко Александр Владимирович")
        self.assertEqual(normalized[0][7], TOP_MANAGER_NAME)
        self.assertEqual(normalized[0][9], "Готово")

    def test_build_structure_index_uses_department_codes(self) -> None:
        values = [
            ["№", "Тип", "Текст", "X", "Y"],
            ["1", "ФИО", "Иванов Иван Иванович", "10", "20"],
            ["2", "Код_подразделения", "3-ООО", "15", "30"],
        ]

        structure_index, department_nodes = build_structure_index(values)

        self.assertIn("Иванов Иван Иванович", structure_index)
        self.assertEqual(len(department_nodes), 1)
        self.assertEqual(department_nodes[0].text, "3-ООО")

    def test_resolve_manager_name_uses_explicit_hierarchy(self) -> None:
        row = parse_template_rows(
            [
                ["№", "ФИО", "Подразделение", "ФИО_руководителя", "ФИО_замещающего", "ФИО_топ_руководителя", "Комментарий"],
                ["1", "Канева Валерия Игоревна", "", "", "", "", ""],
            ]
        )[0]

        self.assertEqual(resolve_manager_name(row), "Кислицын Максим Анатольевич")


if __name__ == "__main__":
    unittest.main()
