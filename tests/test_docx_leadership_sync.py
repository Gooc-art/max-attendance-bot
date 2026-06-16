from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from docx_leadership_sync import (
    EmployeeSheetRow,
    TOP_MANAGER_NAME,
    build_employee_index,
    build_department_id,
    build_department_sheet_rows,
    build_employee_updates,
    build_employee_backfill_updates,
    build_employee_role_updates,
    build_department_manager_map,
    build_normalized_rows,
    canonicalize_department_name,
    normalize_department_key,
    StructureNode,
    resolve_department_manager,
    build_structure_index,
    parse_template_rows,
    resolve_manager_name,
    resolve_manager_user_id,
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
            "Иванов Иван Иванович": EmployeeSheetRow(row_number=2, employee_name="Иванов Иван Иванович", employee_user_id="max_001"),
            "Петров Петр Сергеевич": EmployeeSheetRow(row_number=3, employee_name="Петров Петр Сергеевич", employee_user_id="max_002"),
        }

        updates = build_employee_updates(rows, employee_index, {}, [], {})

        self.assertEqual(
            [(item.row_number, item.column, item.value) for item in updates],
            [(2, "G", "Отдел продаж"), (2, "E", "Петров Петр Сергеевич"), (2, "F", "max_002")],
        )

    def test_build_employee_updates_uses_structure_department_override(self) -> None:
        rows = parse_template_rows(
            [
                ["№", "ФИО", "Подразделение", "ФИО_руководителя", "ФИО_замещающего", "ФИО_топ_руководителя", "Комментарий"],
                ["1", "Антипина Луиза Николаевна", "", "", "", "", ""],
            ]
        )
        employee_index = {
            "Антипина Луиза Николаевна": EmployeeSheetRow(row_number=2, employee_name="Антипина Луиза Николаевна", employee_user_id="max_001"),
            "Слабенко Александр Владимирович": EmployeeSheetRow(row_number=3, employee_name="Слабенко Александр Владимирович", employee_user_id="max_002"),
        }

        updates = build_employee_updates(rows, employee_index, {"Антипина Луиза Николаевна": object()}, [], {})

        self.assertIn((2, "G", "8-ОРиУН"), [(item.row_number, item.column, item.value) for item in updates])
        self.assertIn((2, "F", "max_002"), [(item.row_number, item.column, item.value) for item in updates])

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

        normalized = build_normalized_rows(rows, employee_index, {}, [], {})

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
                ["Слабенко Александр Владимирович", "max_002"],
            ]
        )

        normalized = build_normalized_rows(rows, employee_index, {}, [], {})

        self.assertEqual(normalized[0][4], "Слабенко Александр Владимирович")
        self.assertEqual(normalized[0][5], "max_002")
        self.assertEqual(normalized[0][7], TOP_MANAGER_NAME)
        self.assertEqual(normalized[0][9], "Готово")

    def test_build_structure_index_uses_department_codes(self) -> None:
        values = [
            ["№", "Тип", "Текст", "X", "Y"],
            ["1", "ФИО", "Иванов Иван Иванович", "10", "20"],
            ["2", "Код_подразделения", "3-ООО", "15", "30"],
        ]

        structure_index, department_nodes, fio_nodes = build_structure_index(values)

        self.assertIn("Иванов Иван Иванович", structure_index)
        self.assertEqual(len(department_nodes), 1)
        self.assertEqual(department_nodes[0].text, "3-ООО")
        self.assertEqual(len(fio_nodes), 1)

    def test_build_department_manager_map_uses_nearest_fio_above_department(self) -> None:
        fio_nodes = [
            # Top manager is intentionally farther away.
            StructureNode(kind="ФИО", text="Посунько Руслан Юрьевич", x=0, y=10),
            StructureNode(kind="ФИО", text="Антипина Луиза Николаевна", x=0, y=100),
        ]
        department_nodes = [
            StructureNode(kind="Код_подразделения", text="8-ОРиУН", x=10, y=130),
        ]

        mapping = build_department_manager_map(fio_nodes, department_nodes)

        self.assertEqual(mapping[normalize_department_key("8-ОРиУН")], "Антипина Луиза Николаевна")

    def test_build_employee_updates_uses_department_manager_when_row_manager_is_blank(self) -> None:
        rows = parse_template_rows(
            [
                ["№", "ФИО", "Подразделение", "ФИО_руководителя", "ФИО_замещающего", "ФИО_топ_руководителя", "Комментарий"],
                ["1", "Иванов Иван Иванович", "", "", "", "", ""],
            ]
        )
        employee_index = {
            "Иванов Иван Иванович": EmployeeSheetRow(row_number=2, employee_name="Иванов Иван Иванович", employee_user_id="max_001"),
            "Клоченок Анастасия Ивановна": EmployeeSheetRow(row_number=3, employee_name="Клоченок Анастасия Ивановна", employee_user_id="max_002"),
        }
        department_manager_map = {"3-ООО": "Клоченок Анастасия Ивановна"}

        updates = build_employee_updates(
            rows,
            employee_index,
            {"Иванов Иван Иванович": StructureNode(kind="ФИО", text="Иванов Иван Иванович", x=10, y=20)},
            [StructureNode(kind="Код_подразделения", text="3-ООО", x=15, y=30)],
            department_manager_map,
        )

        self.assertIn((2, "E", "Клоченок Анастасия Ивановна"), [(item.row_number, item.column, item.value) for item in updates])
        self.assertIn((2, "F", "max_002"), [(item.row_number, item.column, item.value) for item in updates])

    def test_build_employee_backfill_updates_fills_blank_manager_from_department(self) -> None:
        employee_index = {
            "Иванов Иван Иванович": EmployeeSheetRow(
                row_number=2,
                employee_name="Иванов Иван Иванович",
                employee_user_id="max_001",
                department_name="3-ООО",
                manager_name="",
                manager_user_id="",
            ),
            "Клоченок Анастасия Ивановна": EmployeeSheetRow(
                row_number=3,
                employee_name="Клоченок Анастасия Ивановна",
                employee_user_id="max_002",
            )
        }
        department_manager_map = {"3-ООО": "Клоченок Анастасия Ивановна"}

        updates = build_employee_backfill_updates(employee_index, department_manager_map)

        update_tuples = [(item.row_number, item.column, item.value) for item in updates]
        self.assertIn((2, "E", "Клоченок Анастасия Ивановна"), update_tuples)
        self.assertIn((2, "F", "max_002"), update_tuples)

    def test_build_employee_backfill_updates_overwrites_wrong_manager_for_regular_employee(self) -> None:
        employee_index = {
            "Иванов Иван Иванович": EmployeeSheetRow(
                row_number=2,
                employee_name="Иванов Иван Иванович",
                employee_user_id="max_001",
                department_name="3-ООО",
                manager_name="Случайный Руководитель",
                manager_user_id="old_mgr",
            ),
            "Клоченок Анастасия Ивановна": EmployeeSheetRow(
                row_number=3,
                employee_name="Клоченок Анастасия Ивановна",
                employee_user_id="max_002",
            )
        }
        department_manager_map = {"3-ООО": "Клоченок Анастасия Ивановна"}

        updates = build_employee_backfill_updates(employee_index, department_manager_map)

        update_tuples = [(item.row_number, item.column, item.value) for item in updates]
        self.assertIn((2, "E", "Клоченок Анастасия Ивановна"), update_tuples)
        self.assertIn((2, "F", "max_002"), update_tuples)

    def test_resolve_department_manager_matches_messy_department_names(self) -> None:
        department_manager_map = {"1-ОКПКиПиБ": "Сафонов Алексей Валентинович"}

        self.assertEqual(
            resolve_department_manager("1. ОКПКиПБ", department_manager_map),
            "Сафонов Алексей Валентинович",
        )

    def test_resolve_department_manager_uses_explicit_override(self) -> None:
        self.assertEqual(
            resolve_department_manager("22. ПО1", {}),
            "Марникова Наталья Евгеньевна",
        )

    def test_build_employee_backfill_updates_clears_top_manager_manager_cell(self) -> None:
        employee_index = {
            TOP_MANAGER_NAME: EmployeeSheetRow(
                row_number=2,
                employee_name=TOP_MANAGER_NAME,
                employee_user_id="max_001",
                department_name="",
                manager_name="Старый Руководитель",
                manager_user_id="max_old",
            )
        }

        updates = build_employee_backfill_updates(employee_index, {})

        self.assertEqual([(item.row_number, item.column, item.value) for item in updates], [(2, "E", ""), (2, "F", "")])

    def test_resolve_manager_name_uses_explicit_hierarchy(self) -> None:
        row = parse_template_rows(
            [
                ["№", "ФИО", "Подразделение", "ФИО_руководителя", "ФИО_замещающего", "ФИО_топ_руководителя", "Комментарий"],
                ["1", "Канева Валерия Игоревна", "", "", "", "", ""],
            ]
        )[0]

        self.assertEqual(resolve_manager_name(row, "", {}), "Кислицын Максим Анатольевич")

    def test_resolve_manager_user_id_returns_employee_user_id_for_manager_name(self) -> None:
        employee_index = {
            "Клоченок Анастасия Ивановна": EmployeeSheetRow(
                row_number=2,
                employee_name="Клоченок Анастасия Ивановна",
                employee_user_id="max_002",
            )
        }

        self.assertEqual(resolve_manager_user_id("Клоченок Анастасия Ивановна", employee_index), "max_002")

    def test_canonicalize_department_name_uses_expected_display_name(self) -> None:
        self.assertEqual(canonicalize_department_name("1. ОКПКиПБ"), "1. ОКПКиПиБ")
        self.assertEqual(canonicalize_department_name("22. ПО1"), "22. ПО№1")
        self.assertEqual(canonicalize_department_name("3. ОО"), "3. ООО")

    def test_build_department_id_uses_department_number(self) -> None:
        self.assertEqual(build_department_id("0. Руководство"), "DEP001")
        self.assertEqual(build_department_id("1. ОКПКиПиБ"), "DEP002")
        self.assertEqual(build_department_id("22. ПО№1"), "DEP023")

    def test_build_department_sheet_rows_builds_manager_and_manager_id(self) -> None:
        employee_index = {
            "Иванов Иван Иванович": EmployeeSheetRow(
                row_number=2,
                employee_name="Иванов Иван Иванович",
                employee_user_id="max_001",
                department_name="1. ОКПКиПБ",
            ),
            "Сафонов Алексей Валентинович": EmployeeSheetRow(
                row_number=3,
                employee_name="Сафонов Алексей Валентинович",
                employee_user_id="max_mgr",
                department_name="1. ОКПКиПиБ",
            ),
        }

        rows = build_department_sheet_rows(employee_index)

        self.assertEqual(rows[0][0], "DEP002")
        self.assertEqual(rows[0][1], "1. ОКПКиПиБ")
        self.assertEqual(rows[0][4], "Сафонов Алексей Валентинович")
        self.assertEqual(rows[0][5], "max_mgr")

    def test_build_employee_role_updates_marks_department_managers_as_manager(self) -> None:
        employee_index = {
            "Сафонов Алексей Валентинович": EmployeeSheetRow(
                row_number=2,
                employee_name="Сафонов Алексей Валентинович",
                employee_user_id="max_mgr",
                role="Сотрудник",
            ),
            "Иванов Иван Иванович": EmployeeSheetRow(
                row_number=3,
                employee_name="Иванов Иван Иванович",
                employee_user_id="max_001",
                role="Сотрудник",
            ),
        }

        updates = build_employee_role_updates(employee_index)

        self.assertEqual([(item.row_number, item.column, item.value) for item in updates], [(2, "I", "Начальник отдела")])


if __name__ == "__main__":
    unittest.main()
