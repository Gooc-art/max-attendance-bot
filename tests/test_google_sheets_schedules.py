from __future__ import annotations

import unittest
from datetime import date

from app.integrations.google_sheets.schedules import GoogleSheetsScheduleService


class _FakeGoogleSheetsScheduleService(GoogleSheetsScheduleService):
    def __init__(self, values):
        super().__init__(spreadsheet_id="sheet-id", service_account_file=__file__, schedule_range="Графики!A:X")
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
                    "Понедельник_окончание",
                    "Вторник_начало",
                    "Вторник_окончание",
                    "Среда_начало",
                    "Среда_окончание",
                    "Четверг_начало",
                    "Четверг_окончание",
                    "Пятница_начало",
                    "Пятница_окончание",
                    "Суббота_начало",
                    "Суббота_окончание",
                    "Воскресенье_начало",
                    "Воскресенье_окончание",
                    "Допустимое_опоздание_мин",
                    "Обед_с",
                    "Обед_по",
                    "Обед_мин",
                    "План_минут_в_день",
                    "Тип_обеда",
                    "Активен",
                    "Комментарий",
                ],
                [
                    "ГР003",
                    "Пятидневка - Девушки 08:30-12:30 / 14:00-17:15",
                    "08:30",
                    "17:15",
                    "08:30",
                    "17:15",
                    "08:30",
                    "17:15",
                    "08:30",
                    "17:15",
                    "08:30",
                    "17:15",
                    "",
                    "",
                    "",
                    "",
                    "10",
                    "12:30",
                    "14:00",
                    "90",
                    "429",
                    "fixed",
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
        self.assertEqual(record.lunch_start, "12:30")
        self.assertEqual(record.lunch_end, "14:00")
        self.assertEqual(record.lunch_minutes, 90)
        self.assertEqual(record.planned_minutes_per_day, 429)
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
        self.assertEqual(
            service.resolve_planned_minutes(
                schedule_id="ГР003",
                event_date=date(2026, 5, 4),
            ),
            429,
        )
        self.assertEqual(service.resolve_lunch_window(schedule_id="ГР003"), ("12:30", "14:00"))
        self.assertEqual(service.resolve_lunch_mode(schedule_id="ГР003"), "fixed")

    def test_uses_cached_records_when_refresh_fails(self) -> None:
        service = _FakeGoogleSheetsScheduleService(
            [
                [
                    "ID_графика",
                    "Наименование_графика",
                    "Понедельник_начало",
                    "Понедельник_окончание",
                    "Вторник_начало",
                    "Вторник_окончание",
                    "Среда_начало",
                    "Среда_окончание",
                    "Четверг_начало",
                    "Четверг_окончание",
                    "Пятница_начало",
                    "Пятница_окончание",
                    "Суббота_начало",
                    "Суббота_окончание",
                    "Воскресенье_начало",
                    "Воскресенье_окончание",
                    "Допустимое_опоздание_мин",
                    "Обед_с",
                    "Обед_по",
                    "Обед_мин",
                    "План_минут_в_день",
                    "Тип_обеда",
                    "Активен",
                    "Комментарий",
                ],
                [
                    "ГР004",
                    "Пятидневка - Парни 08:30-12:30 / 14:00-18:15",
                    "08:30",
                    "18:15",
                    "08:30",
                    "18:15",
                    "08:30",
                    "18:15",
                    "08:30",
                    "18:15",
                    "08:30",
                    "18:15",
                    "",
                    "",
                    "",
                    "",
                    "15",
                    "12:30",
                    "14:00",
                    "90",
                    "480",
                    "fixed",
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

    def test_resolves_lunch_from_split_schedule_name_when_columns_are_empty(self) -> None:
        service = _FakeGoogleSheetsScheduleService(
            [
                [
                    "ID_графика",
                    "Наименование_графика",
                    "Понедельник_начало",
                    "Понедельник_окончание",
                    "Допустимое_опоздание_мин",
                    "Активен",
                    "Комментарий",
                ],
                [
                    "ГР005",
                    "Пятидневка - Девушки 08:30-12:30 / 14:00-17:15",
                    "08:30",
                    "17:15",
                    "10",
                    "Да",
                    "",
                ],
            ]
        )

        records = service.list_schedules(refresh=True)

        self.assertEqual(len(records), 1)
        self.assertEqual(service.resolve_lunch_window(schedule_id="ГР005"), ("12:30", "14:00"))
        self.assertEqual(service.resolve_lunch_minutes(schedule_id="ГР005"), 90)
        self.assertEqual(
            service.resolve_planned_minutes(
                schedule_id="ГР005",
                event_date=date(2026, 5, 4),
            ),
            429,
        )


if __name__ == "__main__":
    unittest.main()
