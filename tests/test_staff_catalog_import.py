from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from create_google_sheet import SCHEDULE_ROWS, build_department_id_map, build_department_rows, build_staff_rows, infer_schedule_id


class StaffCatalogImportTests(unittest.TestCase):
    def test_build_department_id_map_is_stable(self) -> None:
        catalog = {"departments": {"0. Руководство": [], "1. ОКПКиПБ": []}}

        result = build_department_id_map(catalog)

        self.assertEqual(result["0. Руководство"], "DEP001")
        self.assertEqual(result["1. ОКПКиПБ"], "DEP002")

    def test_build_department_rows_matches_catalog(self) -> None:
        catalog = {"departments": {"0. Руководство": [], "1. ОКПКиПБ": []}}

        rows = build_department_rows(catalog)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], "DEP001")
        self.assertEqual(rows[1][1], "1. ОКПКиПБ")

    def test_build_staff_rows_uses_bindings_and_keeps_missing_ids_blank(self) -> None:
        catalog = {
            "departments": {
                "0. Руководство": ["Иванов Иван Иванович"],
                "1. ОКПКиПБ": ["Петров Петр Петрович"],
            }
        }
        bindings = {
            "1": {"name": "Иванов Иван Иванович", "user_id": 123},
        }

        rows = build_staff_rows(catalog, bindings)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][1], "Иванов Иван Иванович")
        self.assertEqual(rows[0][3], "123")
        self.assertEqual(rows[0][8], "Руководитель")
        self.assertEqual(rows[0][9], "Пятидневка - Парни 08:30-12:30 / 14:00-18:15")
        self.assertEqual(rows[0][10], "ГР004")
        self.assertEqual(rows[1][1], "Петров Петр Петрович")
        self.assertEqual(rows[1][3], "")
        self.assertEqual(rows[1][8], "Сотрудник")
        self.assertEqual(rows[1][9], "Пятидневка - Парни 08:30-12:30 / 14:00-18:15")
        self.assertEqual(rows[1][10], "ГР004")

    def test_build_staff_rows_assigns_female_schedule(self) -> None:
        catalog = {"departments": {"1. ОКПКиПБ": ["Иванова Анна Сергеевна"]}}
        bindings = {"1": {"name": "Иванова Анна Сергеевна", "user_id": 555}}

        rows = build_staff_rows(catalog, bindings)

        self.assertEqual(rows[0][9], "Пятидневка - Девушки 08:30-12:30 / 14:00-17:15")
        self.assertEqual(rows[0][10], "ГР003")

    def test_infer_schedule_id_uses_patronymic_and_first_name(self) -> None:
        self.assertEqual(infer_schedule_id("Иванов Иван Иванович"), "ГР004")
        self.assertEqual(infer_schedule_id("Иванова Анна Сергеевна"), "ГР003")

    def test_schedule_rows_include_day_and_men_shift_patterns(self) -> None:
        schedule_names = [row[1] for row in SCHEDULE_ROWS]

        self.assertIn("Пятидневка - Девушки 08:30-12:30 / 14:00-17:15", schedule_names)
        self.assertIn("Пятидневка - Парни 08:30-12:30 / 14:00-18:15", schedule_names)


if __name__ == "__main__":
    unittest.main()
