from __future__ import annotations

import unittest
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.integrations.google_sheets.directory import GoogleSheetsEmployeeRecord
from app.services.office_sealing import OfficeSealException, OfficeSealJournalRow, OfficeSealingService


class _Directory:
    def __init__(self) -> None:
        self.employee = GoogleSheetsEmployeeRecord(
            employee_id="EMP001",
            employee_name="Иванова Анна Ивановна",
            employee_user_id="1001",
            manager_user_id="2001",
            office="314",
            schedule_name="Пятидневка - Девушки 08:30-12:30 / 14:00-17:15",
            is_active=True,
        )
        self.subordinate = self.employee
        self.missing = GoogleSheetsEmployeeRecord(
            employee_id="EMP002",
            employee_name="Петров Петр Петрович",
            employee_user_id="1002",
            manager_user_id="2001",
            office="314",
            schedule_name="Пятидневка - Парни 08:30-12:30 / 14:00-18:15",
            is_active=True,
        )
        self.other_office = GoogleSheetsEmployeeRecord(
            employee_id="EMP003",
            employee_name="Сидоров Сидор Сидорович",
            employee_user_id="1003",
            manager_user_id="2001",
            office="315",
            schedule_name="Пятидневка - Парни 08:30-12:30 / 14:00-18:15",
            is_active=True,
        )

    def get_by_user_id(self, user_id: str):
        return {
            "1001": self.employee,
            "1002": self.missing,
            "1003": self.other_office,
        }.get(user_id)

    def get_by_manager_user_id(self, manager_user_id: str, refresh: bool = False):
        return [self.subordinate, self.missing, self.other_office] if manager_user_id == "2001" else []

    def list_employees(self):
        return [self.subordinate, self.missing, self.other_office]


class _EmployeeRepository:
    def get_by_user_id(self, user_id: str):
        return None

    def get_by_manager_user_id(self, manager_user_id: str):
        return []

    def list_recent(self, limit: int = 5000):
        return []


class _Journal:
    def __init__(self) -> None:
        self.rows = []
        self.exceptions = []

    def has_entry(self, *, date: str, employee_id: str) -> bool:
        return any(row.date == date and row.employee_id == employee_id for row in self.rows)

    def has_office_entry(self, *, date: str, office: str) -> bool:
        return any(row.date == date and row.office == office for row in self.rows)

    def append_once(self, row: OfficeSealJournalRow) -> bool:
        if self.has_office_entry(date=row.date, office=row.office):
            return False
        self.rows.append(row)
        return True

    def list_rows(self):
        return list(self.rows)

    def list_exceptions(self):
        return list(self.exceptions)

    def office_exception(self, *, date: str, office: str):
        for row in self.exceptions:
            if not row.is_active or row.office != office:
                continue
            if row.date_from and date < row.date_from:
                continue
            if row.date_to and date > row.date_to:
                continue
            return row
        return None


class OfficeSealingServiceTests(unittest.TestCase):
    def _service(self) -> tuple[OfficeSealingService, _Journal]:
        journal = _Journal()
        self.sent_messages = []
        service = OfficeSealingService(
            directory_service=_Directory(),
            employee_repository=_EmployeeRepository(),
            journal_service=journal,
            max_client=SimpleNamespace(
                get_message=lambda message_id: {},
                send_message=lambda **kwargs: self.sent_messages.append(kwargs) or {"ok": True},
            ),
        )
        service.timezone_name = "Europe/Moscow"
        service.public_base_url = "https://bot.example"
        return service, journal

    def test_start_rejects_outside_work_window(self) -> None:
        service, _ = self._service()

        result = service.start("1001", now=datetime(2026, 6, 11, 17, 59, tzinfo=ZoneInfo("Europe/Moscow")))

        self.assertFalse(result.ok)
        self.assertIn("18:00 до 22:00", result.text)

    def test_start_allows_mark_inside_work_window(self) -> None:
        service, _ = self._service()

        result = service.start("1001", now=datetime(2026, 6, 11, 18, 1, tzinfo=ZoneInfo("Europe/Moscow")))

        self.assertTrue(result.ok)
        self.assertIn("без фото", result.text)
        self.assertEqual(result.employee.office, "314")

    def test_mark_sealed_appends_journal_once_per_office_and_notifies_mates(self) -> None:
        service, journal = self._service()

        result = service.mark_sealed(
            user_id="1001",
            now=datetime(2026, 6, 11, 18, 5, tzinfo=ZoneInfo("Europe/Moscow")),
        )

        self.assertTrue(result.ok)
        self.assertEqual(len(journal.rows), 1)
        self.assertEqual(journal.rows[0].employee_id, "EMP001")
        self.assertEqual(journal.rows[0].office, "314")
        self.assertEqual(journal.rows[0].photo_url, "")
        self.assertEqual(len(self.sent_messages), 1)
        self.assertEqual(self.sent_messages[0]["user_id"], 1002)
        self.assertIn("Кабинет №314 уже опломбирован сегодня", self.sent_messages[0]["text"])
        self.assertNotIn("Фото:", self.sent_messages[0]["text"])

        duplicate = service.mark_sealed(
            user_id="1002",
            now=datetime(2026, 6, 11, 18, 6, tzinfo=ZoneInfo("Europe/Moscow")),
        )
        self.assertFalse(duplicate.ok)
        self.assertEqual(duplicate.text, "Кабинет №314 уже опломбирован сегодня.")

    def test_submit_photo_kept_as_compatibility_path_without_photo_requirement(self) -> None:
        service, journal = self._service()

        result = service.submit_photo(
            user_id="1001",
            attachments=[],
            now=datetime(2026, 6, 11, 18, 5, tzinfo=ZoneInfo("Europe/Moscow")),
        )

        self.assertTrue(result.ok)
        self.assertEqual(len(journal.rows), 1)
        self.assertEqual(journal.rows[0].photo_url, "")

    def test_manager_summary_includes_marked_and_missing_subordinates(self) -> None:
        service, journal = self._service()
        journal.rows.append(
            OfficeSealJournalRow(
                date="2026-06-11",
                time="18:05",
                employee_id="EMP001",
                office="314",
                photo_url="https://bot.example/photo.jpg",
            )
        )

        summary = service.build_manager_summary("2001", now=datetime(2026, 6, 11, 22, 0, tzinfo=ZoneInfo("Europe/Moscow")))

        self.assertIn("Опломбировано кабинетов: 1/2", summary)
        self.assertIn("каб. 314, 18:05, опломбировал: Иванова Анна Ивановна", summary)
        self.assertIn("фото: https://bot.example/photo.jpg", summary)
        self.assertIn("каб. 315: Сидоров Сидор Сидорович", summary)

    def test_manager_summary_omits_photo_when_new_mark_has_no_photo(self) -> None:
        service, journal = self._service()
        journal.rows.append(
            OfficeSealJournalRow(
                date="2026-06-11",
                time="18:05",
                employee_id="EMP001",
                office="314",
                photo_url="",
            )
        )

        summary = service.build_manager_summary("2001", now=datetime(2026, 6, 11, 22, 0, tzinfo=ZoneInfo("Europe/Moscow")))

        self.assertIn("каб. 314, 18:05, опломбировал: Иванова Анна Ивановна", summary)
        self.assertNotIn("фото:", summary)

    def test_employee_office_status_shows_mates_and_today_status(self) -> None:
        service, journal = self._service()
        journal.rows.append(
            OfficeSealJournalRow(
                date="2026-06-11",
                time="18:05",
                employee_id="EMP001",
                office="314",
                photo_url="https://bot.example/photo.jpg",
            )
        )

        status = service.build_employee_office_status("1002", now=datetime(2026, 6, 11, 19, 0, tzinfo=ZoneInfo("Europe/Moscow")))

        self.assertIn("Кабинет: №314", status)
        self.assertIn("Иванова Анна Ивановна, Петров Петр Петрович", status)
        self.assertIn("Статус сегодня: опломбирован", status)
        self.assertIn("Фото: https://bot.example/photo.jpg", status)

    def test_employee_office_status_omits_photo_when_new_mark_has_no_photo(self) -> None:
        service, journal = self._service()
        journal.rows.append(
            OfficeSealJournalRow(
                date="2026-06-11",
                time="18:05",
                employee_id="EMP001",
                office="314",
                photo_url="",
            )
        )

        status = service.build_employee_office_status("1002", now=datetime(2026, 6, 11, 19, 0, tzinfo=ZoneInfo("Europe/Moscow")))

        self.assertIn("Статус сегодня: опломбирован", status)
        self.assertIn("Время: 18:05", status)
        self.assertNotIn("Фото:", status)

    def test_gender_reminders_send_simple_ack_button_without_journal_filter(self) -> None:
        service, journal = self._service()
        journal.exceptions.append(
            OfficeSealException(
                office="314",
                date_from="2026-06-11",
                date_to="2026-06-11",
                reason="Ремонт",
                is_active=True,
            )
        )

        female_sent = service.send_reminders_for_gender("female", now=datetime(2026, 6, 11, 17, 10, tzinfo=ZoneInfo("Europe/Moscow")))
        male_sent = service.send_reminders_for_gender("male", now=datetime(2026, 6, 11, 17, 55, tzinfo=ZoneInfo("Europe/Moscow")))

        self.assertEqual(female_sent, 1)
        self.assertEqual(male_sent, 2)
        self.assertEqual(self.sent_messages[0]["user_id"], 1001)
        self.assertEqual(
            self.sent_messages[0]["text"],
            "Напоминание: пожалуйста, не забудь закрыть дверь и опломбировать кабинет.",
        )
        self.assertEqual(self.sent_messages[0]["buttons"][0].title, "Спасибо за напоминание")
        self.assertEqual(self.sent_messages[0]["buttons"][0].action, "office_seal.reminder_ack")
        self.assertEqual(len(journal.rows), 0)

    def test_gender_reminders_remember_sent_message_for_ack_cleanup(self) -> None:
        cursor = SimpleNamespace(saved=[])
        cursor.set = lambda **kwargs: cursor.saved.append(kwargs)
        service, _journal = self._service()
        service.max_client.send_message = lambda **kwargs: {"mid": "reminder-mid"}
        service.cursor_store = cursor

        sent = service.send_reminders_for_gender(
            "female",
            now=datetime(2026, 6, 11, 17, 10, tzinfo=ZoneInfo("Europe/Moscow")),
        )

        self.assertEqual(sent, 1)
        self.assertEqual(
            cursor.saved,
            [
                {
                    "conversation_key": "user:1001",
                    "chat_id": "",
                    "user_id": "1001",
                    "message_id": "reminder-mid",
                }
            ],
        )

    def test_gender_reminders_skip_duplicate_user_ids(self) -> None:
        service, _journal = self._service()
        employee = service.directory_service.employee
        service.directory_service.list_employees = lambda: [employee, employee]

        sent = service.send_reminders_for_gender(
            "female",
            now=datetime(2026, 6, 11, 17, 10, tzinfo=ZoneInfo("Europe/Moscow")),
        )

        self.assertEqual(sent, 1)
        self.assertEqual(len(self.sent_messages), 1)


if __name__ == "__main__":
    unittest.main()
