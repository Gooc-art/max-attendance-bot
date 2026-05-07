from __future__ import annotations

import unittest
from datetime import date

from app.integrations.google_sheets.schedules import GoogleSheetsScheduleService


class _FakeGoogleSheetsScheduleService(GoogleSheetsScheduleService):
    def __init__(self, values):
        super().__init__(spreadsheet_id="sheet-id", service_account_file=__file__, schedule_range="Графики!A:L")
        self._values = values

    def is_configured(self) -> bool:
        return True

    def _fetch_values(self):
        return self._values


class GoogleSheetsScheduleServiceTests(unittest.TestCase):
    def test_parse_values_and_resolve_by_weekday(self) -> None:
        service = _FakeGoogleSheetsScheduleService(
            [
                [
                    "ID_графика",
                    "Наименование_графика",
                    "Понедельник_начало",
                    "Вторник_начало",
                    "Среда_начало",
                    "Четверг_начало",
                    "Пятница_начало",
                    "Суббота_начало",
                    "Воскресенье_начало",
                    "Допустимое_опоздание_мин",
                    "Активен",
                    "Комментарий",
                ],
                [
                    "ГР003",
                    "Пятидневка - Девушки 08:30-12:30 / 14:00-17:15",
                    "08:30",
                    "08:30",
                    "08:30",
                    "08:30",
                    "08:30",
                    "",
                    "",
                    "10",
                    "Да",
                    "Обед 12:30-14:00",
                ],
            ]
        )

        records = service.list_schedules(refresh=True)

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.schedule_id, "ГР003")
        self.assertEqual(record.schedule_name, "Пятидневка - Девушки 08:30-12:30 / 14:00-17:15")
        self.assertEqual(record.late_after_minutes, 10)
        self.assertEqual(
            service.resolve_planned_start(
                schedule_id="ГР003",
                event_date=date(2026, 5, 4),
            ),
            "08:30",
        )
        self.assertEqual(
            service.resolve_planned_start(
                schedule_id="ГР003",
                event_date=date(2026, 5, 9),
            ),
            "",
        )


if __name__ == "__main__":
    unittest.main()
