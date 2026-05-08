from __future__ import annotations

import unittest
from datetime import date

from app.integrations.google_sheets.schedules import GoogleSheetsScheduleService


class _FakeGoogleSheetsScheduleService(GoogleSheetsScheduleService):
    def __init__(self, values):
        super().__init__(spreadsheet_id="sheet-id", service_account_file=__file__, schedule_range="Графики!A:L")
        self._values = values
        self.fetch_calls = 0

    def is_configured(self) -> bool:
        return True

    def _fetch_values(self):
        self.fetch_calls += 1
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
        self.assertEqual(
            service.resolve_planned_end(
                schedule_id="ГР003",
                event_date=date(2026, 5, 4),
            ),
            "17:15",
        )

    def test_uses_cached_records_when_refresh_fails(self) -> None:
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
                    "ГР004",
                    "Пятидневка - Парни 08:30-12:30 / 14:00-18:15",
                    "08:30",
                    "08:30",
                    "08:30",
                    "08:30",
                    "08:30",
                    "",
                    "",
                    "15",
                    "Да",
                    "",
                ],
            ]
        )
        first_records = service.list_schedules(refresh=True)
        self.assertEqual(len(first_records), 1)

        def _raise():
            raise RuntimeError("quota exceeded")

        service._fetch_values = _raise  # type: ignore[assignment]

        cached_records = service.list_schedules(refresh=True)
        self.assertEqual(len(cached_records), 1)
        self.assertEqual(cached_records[0].schedule_id, "ГР004")
        self.assertEqual(
            service.resolve_planned_end(
                schedule_id="ГР004",
                event_date=date(2026, 5, 4),
            ),
            "18:15",
        )


if __name__ == "__main__":
    unittest.main()
