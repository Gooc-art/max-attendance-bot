from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Iterable, List, Optional
from urllib.request import Request, urlopen
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.integrations.google_sheets.directory import GoogleSheetsDirectoryService, GoogleSheetsEmployeeRecord
from app.integrations.max.client import MaxApiClient
from app.repositories.employee_directory_repository import EmployeeDirectoryRepository
from app.services.bot_message_cursor import bot_message_cursor_store
from app.schemas.max import MaxAttachment, MaxOutboundButton


OFFICE_SEAL_JOURNAL_HEADERS = ["Дата", "Время", "ID_сотрудника", "Кабинет", "Ссылка_на_фото"]
OFFICE_SEAL_EXCEPTION_HEADERS = ["Кабинет", "Дата_начала", "Дата_окончания", "Причина", "Активно", "Комментарий"]
PHOTO_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


@dataclass(frozen=True)
class OfficeSealEmployee:
    employee_id: str
    user_id: str
    name: str
    manager_user_id: str
    office: str
    is_active: bool
    gender: str = ""


@dataclass(frozen=True)
class OfficeSealJournalRow:
    date: str
    time: str
    employee_id: str
    office: str
    photo_url: str


@dataclass(frozen=True)
class OfficeSealException:
    office: str
    date_from: str
    date_to: str
    reason: str
    is_active: bool
    comment: str = ""


@dataclass(frozen=True)
class OfficeSealStartResult:
    ok: bool
    text: str
    employee: Optional[OfficeSealEmployee] = None


@dataclass(frozen=True)
class OfficeSealSubmitResult:
    ok: bool
    text: str
    photo_url: str = ""


class OfficeSealJournalService:
    def __init__(self, spreadsheet_id: str | None = None, service_account_file: str | None = None) -> None:
        settings = get_settings()
        self.spreadsheet_id = spreadsheet_id or settings.google_sheets_spreadsheet_id
        self.service_account_file = service_account_file or settings.google_service_account_file
        self._sheets_service = None
        self._lock = threading.Lock()

    def is_configured(self) -> bool:
        return bool(self.spreadsheet_id and self.service_account_file and Path(self.service_account_file).exists())

    def list_rows(self) -> List[OfficeSealJournalRow]:
        if not self.is_configured():
            return []
        self.ensure_sheet()
        values = (
            self._service()
            .spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range="Журнал!A:E")
            .execute()
            .get("values", [])
        )
        rows: List[OfficeSealJournalRow] = []
        for raw in values[1:]:
            cells = [str(item).strip() for item in raw]
            cells.extend([""] * (5 - len(cells)))
            if not any(cells):
                continue
            rows.append(
                OfficeSealJournalRow(
                    date=cells[0],
                    time=cells[1],
                    employee_id=cells[2],
                    office=cells[3],
                    photo_url=cells[4],
                )
            )
        return rows

    def has_entry(self, *, date: str, employee_id: str) -> bool:
        return any(row.date == date and row.employee_id == employee_id for row in self.list_rows())

    def has_office_entry(self, *, date: str, office: str) -> bool:
        office_value = self._normalize_office(office)
        return any(row.date == date and self._normalize_office(row.office) == office_value for row in self.list_rows())

    def append_once(self, row: OfficeSealJournalRow) -> bool:
        if not self.is_configured():
            return False
        with self._lock:
            self.ensure_sheet()
            if self.has_office_entry(date=row.date, office=row.office):
                return False
            (
                self._service()
                .spreadsheets()
                .values()
                .append(
                    spreadsheetId=self.spreadsheet_id,
                    range="Журнал!A:E",
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body={"values": [[row.date, row.time, row.employee_id, row.office, row.photo_url]]},
                )
                .execute()
            )
            return True

    def list_exceptions(self) -> List[OfficeSealException]:
        if not self.is_configured():
            return []
        self.ensure_exception_sheet()
        values = (
            self._service()
            .spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range="Исключения_кабинетов!A:F")
            .execute()
            .get("values", [])
        )
        rows: List[OfficeSealException] = []
        for raw in values[1:]:
            cells = [str(item).strip() for item in raw]
            cells.extend([""] * (6 - len(cells)))
            if not any(cells):
                continue
            rows.append(
                OfficeSealException(
                    office=cells[0],
                    date_from=cells[1],
                    date_to=cells[2],
                    reason=cells[3],
                    is_active=self._to_bool(cells[4], default=True),
                    comment=cells[5],
                )
            )
        return rows

    def office_exception(self, *, date: str, office: str) -> OfficeSealException | None:
        office_value = self._normalize_office(office)
        if not office_value:
            return None
        for row in self.list_exceptions():
            if not row.is_active or self._normalize_office(row.office) != office_value:
                continue
            if row.date_from and date < row.date_from:
                continue
            if row.date_to and date > row.date_to:
                continue
            return row
        return None

    @staticmethod
    def _normalize_office(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip()).lower()

    def ensure_sheet(self) -> None:
        metadata = self._service().spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
        sheets = metadata.get("sheets", [])
        if not any(item.get("properties", {}).get("title") == "Журнал" for item in sheets):
            (
                self._service()
                .spreadsheets()
                .batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body={"requests": [{"addSheet": {"properties": {"title": "Журнал"}}}]},
                )
                .execute()
            )
        values = (
            self._service()
            .spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range="Журнал!A1:E1")
            .execute()
            .get("values", [])
        )
        if not values or values[0][:5] != OFFICE_SEAL_JOURNAL_HEADERS:
            (
                self._service()
                .spreadsheets()
                .values()
                .update(
                    spreadsheetId=self.spreadsheet_id,
                    range="Журнал!A1:E1",
                    valueInputOption="USER_ENTERED",
                    body={"values": [OFFICE_SEAL_JOURNAL_HEADERS]},
                )
                .execute()
            )

    def ensure_exception_sheet(self) -> None:
        metadata = self._service().spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
        sheets = metadata.get("sheets", [])
        if not any(item.get("properties", {}).get("title") == "Исключения_кабинетов" for item in sheets):
            (
                self._service()
                .spreadsheets()
                .batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body={"requests": [{"addSheet": {"properties": {"title": "Исключения_кабинетов"}}}]},
                )
                .execute()
            )
        values = (
            self._service()
            .spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range="Исключения_кабинетов!A1:F1")
            .execute()
            .get("values", [])
        )
        if not values or values[0][:6] != OFFICE_SEAL_EXCEPTION_HEADERS:
            (
                self._service()
                .spreadsheets()
                .values()
                .update(
                    spreadsheetId=self.spreadsheet_id,
                    range="Исключения_кабинетов!A1:F1",
                    valueInputOption="USER_ENTERED",
                    body={"values": [OFFICE_SEAL_EXCEPTION_HEADERS]},
                )
                .execute()
            )

    @staticmethod
    def _to_bool(value: str, default: bool = False) -> bool:
        raw = str(value or "").strip().lower()
        if not raw:
            return default
        return raw in {"1", "true", "yes", "on", "да", "активно"}

    def _service(self):
        if self._sheets_service is not None:
            return self._sheets_service
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        credentials = service_account.Credentials.from_service_account_file(
            self.service_account_file,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        self._sheets_service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        return self._sheets_service


class OfficeSealingService:
    def __init__(
        self,
        *,
        directory_service: GoogleSheetsDirectoryService | None = None,
        employee_repository: EmployeeDirectoryRepository | None = None,
        journal_service: OfficeSealJournalService | None = None,
        max_client: MaxApiClient | None = None,
        cursor_store=None,
    ) -> None:
        settings = get_settings()
        self.directory_service = directory_service or GoogleSheetsDirectoryService.from_settings()
        self.employee_repository = employee_repository or EmployeeDirectoryRepository()
        self.journal_service = journal_service or OfficeSealJournalService()
        self.max_client = max_client or MaxApiClient.from_settings()
        self.cursor_store = cursor_store or bot_message_cursor_store
        self.timezone_name = settings.office_seal_company_timezone
        self.window_start = self._parse_time(settings.office_seal_window_start, fallback=time(18, 0))
        self.window_end = self._parse_time(settings.office_seal_window_end, fallback=time(22, 0))
        self.photo_dir = Path(settings.office_seal_photo_dir)
        self.public_base_url = self._normalize_public_base_url(settings.public_base_url)

    def start(self, user_id: str, now: datetime | None = None) -> OfficeSealStartResult:
        current = self._now(now)
        if not self._is_workday(current):
            return OfficeSealStartResult(False, "Отметка доступна только в рабочие дни.")
        if not self._is_in_window(current):
            return OfficeSealStartResult(False, "Кнопка доступна в рабочие дни с 18:00 до 22:00.")

        employee = self.get_employee_by_user_id(user_id)
        if employee is None or not employee.is_active:
            return OfficeSealStartResult(False, "Ты не найден в активном справочнике сотрудников.")
        if not employee.office:
            return OfficeSealStartResult(False, "В справочнике не указан кабинет. Обратись к администратору.")
        exception = self.journal_service.office_exception(date=current.date().isoformat(), office=employee.office)
        if exception is not None:
            return OfficeSealStartResult(False, self._office_exception_text(employee.office, exception))
        if self.journal_service.has_office_entry(date=current.date().isoformat(), office=employee.office):
            return OfficeSealStartResult(False, "Кабинет №{office} уже опломбирован сегодня.".format(office=employee.office))
        return OfficeSealStartResult(True, "Кабинет можно отметить без фото.", employee)

    def mark_sealed(
        self,
        *,
        user_id: str,
        now: datetime | None = None,
    ) -> OfficeSealSubmitResult:
        current = self._now(now)
        if not self._is_workday(current):
            return OfficeSealSubmitResult(False, "Отметка доступна только в рабочие дни.")
        if not self._is_in_window(current):
            return OfficeSealSubmitResult(False, "Кнопка доступна в рабочие дни с 18:00 до 22:00.")
        employee = self.get_employee_by_user_id(user_id)
        if employee is None or not employee.is_active:
            return OfficeSealSubmitResult(False, "Ты не найден в активном справочнике сотрудников.")
        if not employee.office:
            return OfficeSealSubmitResult(False, "В справочнике не указан кабинет. Обратись к администратору.")
        exception = self.journal_service.office_exception(date=current.date().isoformat(), office=employee.office)
        if exception is not None:
            return OfficeSealSubmitResult(False, self._office_exception_text(employee.office, exception))
        if self.journal_service.has_office_entry(date=current.date().isoformat(), office=employee.office):
            return OfficeSealSubmitResult(False, "Кабинет №{office} уже опломбирован сегодня.".format(office=employee.office))

        inserted = self.journal_service.append_once(
            OfficeSealJournalRow(
                date=current.date().isoformat(),
                time=current.strftime("%H:%M"),
                employee_id=employee.employee_id,
                office=employee.office,
                photo_url="",
            )
        )
        if not inserted:
            return OfficeSealSubmitResult(False, "Кабинет №{office} уже опломбирован сегодня.".format(office=employee.office))
        self._notify_office_mates(employee, current.date().isoformat(), "")
        return OfficeSealSubmitResult(
            True,
            "✅ Зафиксировано. Кабинет №{office} опломбирован. Хорошего вечера!".format(office=employee.office),
            photo_url="",
        )

    def submit_photo(
        self,
        *,
        user_id: str,
        attachments: Iterable[MaxAttachment],
        message_id: str = "",
        now: datetime | None = None,
    ) -> OfficeSealSubmitResult:
        return self.mark_sealed(user_id=user_id, now=now)

    def build_manager_summary(self, manager_user_id: str, now: datetime | None = None, only_if_missing: bool = False) -> str:
        current = self._now(now)
        today = current.date().isoformat()
        employees = self.list_active_subordinates(manager_user_id)
        employees = [employee for employee in employees if employee.office]
        if not employees:
            return "У тебя нет активных подчиненных с указанным кабинетом в справочнике."
        employees_by_id = {employee.employee_id: employee for employee in employees}
        offices = self._group_employees_by_office(employees)
        exceptions = {
            office: self.journal_service.office_exception(date=today, office=office)
            for office in offices
        }
        required_offices = {
            office: employees
            for office, employees in offices.items()
            if exceptions.get(office) is None
        }
        journal_by_office = {
            self._normalize_office(row.office): row
            for row in self.journal_service.list_rows()
            if row.date == today
        }
        marked_offices = [office for office in required_offices if self._normalize_office(office) in journal_by_office]
        missing_offices = [office for office in required_offices if self._normalize_office(office) not in journal_by_office]
        if only_if_missing and not missing_offices:
            return ""

        lines = [
            "Сводка по опломбированию кабинетов за {date}".format(date=today),
            "",
            "Опломбировано кабинетов: {marked}/{total}".format(marked=len(marked_offices), total=len(required_offices)),
        ]
        if marked_offices:
            lines.append("")
            lines.append("✅ Опломбированы:")
            for office in marked_offices:
                row = journal_by_office[self._normalize_office(office)]
                sealed_by = employees_by_id.get(row.employee_id)
                sealed_by_name = sealed_by.name if sealed_by else row.employee_id
                line = "- каб. {office}, {time}, опломбировал: {sealed_by}".format(
                    office=row.office or office,
                    time=row.time or "-",
                    sealed_by=sealed_by_name or "-",
                )
                if row.photo_url:
                    line += ", фото: {photo}".format(photo=row.photo_url)
                lines.append(line)
        if missing_offices:
            lines.append("")
            lines.append("❌ Не опломбированы:")
            for office in missing_offices:
                names = ", ".join(employee.name for employee in required_offices[office] if employee.name)
                lines.append("- каб. {office}: {names}".format(name=names, office=office, names=names or "-"))
        excluded_offices = [office for office in offices if exceptions.get(office) is not None]
        if excluded_offices:
            lines.append("")
            lines.append("⏸ Исключены:")
            for office in excluded_offices:
                exception = exceptions[office]
                lines.append("- каб. {office}: {reason}".format(office=office, reason=exception.reason or "исключение"))
        return "\n".join(lines)

    def build_employee_office_status(self, user_id: str, now: datetime | None = None) -> str:
        current = self._now(now)
        today = current.date().isoformat()
        employee = self.get_employee_by_user_id(user_id)
        if employee is None or not employee.is_active:
            return "Ты не найден в активном справочнике сотрудников."
        if not employee.office:
            return "В справочнике для тебя не указан кабинет."
        office_mates = self.list_active_office_mates(employee.office)
        names = ", ".join(item.name for item in office_mates if item.name) or "-"
        exception = self.journal_service.office_exception(date=today, office=employee.office)
        if exception is not None:
            status = self._office_exception_text(employee.office, exception)
        else:
            row = self._office_journal_row(today, employee.office)
            if row is None:
                status = "Статус сегодня: не опломбирован."
            else:
                sealed_by = next((item for item in office_mates if item.employee_id == row.employee_id), None)
                status = (
                    "Статус сегодня: опломбирован.\n"
                    "Кто отметил: {name}\n"
                    "Время: {time}"
                ).format(
                    name=(sealed_by.name if sealed_by else row.employee_id) or "-",
                    time=row.time or "-",
                )
                if row.photo_url:
                    status += "\nФото: {photo}".format(photo=row.photo_url)
        return (
            "Мой кабинет\n\n"
            "Кабинет: №{office}\n"
            "Сотрудники кабинета: {names}\n\n"
            "{status}"
        ).format(office=employee.office, names=names, status=status)

    def send_initial_reminders(self, now: datetime | None = None) -> int:
        return self.send_reminders_for_gender("female", now=now)

    def send_final_reminders(self, now: datetime | None = None) -> int:
        return self.send_reminders_for_gender("male", now=now)

    def send_reminders_for_gender(self, gender: str, now: datetime | None = None) -> int:
        current = self._now(now)
        if not self._is_workday(current):
            return 0
        employees = [
            employee
            for employee in self._all_active_employees()
            if employee.office and employee.gender == gender
        ]
        return self._send_to_employees(employees, "Напоминание: пожалуйста, не забудь закрыть дверь и опломбировать кабинет.")

    @staticmethod
    def acknowledge_reminder() -> str:
        return "Принято, спасибо."

    def send_auto_summaries(self, now: datetime | None = None) -> int:
        manager_ids = self._manager_user_ids()
        sent = 0
        for manager_user_id in manager_ids:
            text = self.build_manager_summary(manager_user_id, now=now, only_if_missing=True)
            if not text:
                continue
            try:
                self.max_client.send_message(user_id=int(manager_user_id), text=text, buttons=[])
                sent += 1
            except ValueError:
                try:
                    self.max_client.send_message(user_id=manager_user_id, text=text, buttons=[])
                    sent += 1
                except Exception:
                    continue
            except Exception:
                continue
        return sent

    def _required_unsealed_offices(self, date: str) -> dict[str, List[OfficeSealEmployee]]:
        employees = [
            employee
            for employee in self._all_active_employees()
            if employee.office
        ]
        offices = self._group_employees_by_office(employees)
        result: dict[str, List[OfficeSealEmployee]] = {}
        for office, office_employees in offices.items():
            if self.journal_service.office_exception(date=date, office=office) is not None:
                continue
            if self.journal_service.has_office_entry(date=date, office=office):
                continue
            result[office] = office_employees
        return result

    def _send_to_employees(self, employees: Iterable[OfficeSealEmployee], text: str) -> int:
        sent = 0
        seen_user_ids: set[str] = set()
        for employee in employees:
            if not employee.user_id:
                continue
            user_id = str(employee.user_id).strip()
            if not user_id or user_id in seen_user_ids:
                continue
            seen_user_ids.add(user_id)
            buttons = [MaxOutboundButton(title="Спасибо за напоминание", action="office_seal.reminder_ack")]
            try:
                response = self.max_client.send_message(user_id=int(user_id), text=text, buttons=buttons)
                self._remember_user_message(user_id, response)
                sent += 1
            except ValueError:
                try:
                    response = self.max_client.send_message(user_id=user_id, text=text, buttons=buttons)
                    self._remember_user_message(user_id, response)
                    sent += 1
                except Exception:
                    continue
            except Exception:
                continue
        return sent

    def _remember_user_message(self, user_id: str, response: dict) -> None:
        message_id = self._extract_message_id(response)
        if not message_id:
            return
        self.cursor_store.set(
            conversation_key=f"user:{user_id}",
            chat_id="",
            user_id=user_id,
            message_id=message_id,
        )

    @staticmethod
    def _extract_message_id(response: dict) -> str:
        if not isinstance(response, dict):
            return ""
        candidates = [response.get("mid"), response.get("message_id")]
        message = response.get("message")
        if isinstance(message, dict):
            candidates.append(message.get("mid"))
            body = message.get("body")
            if isinstance(body, dict):
                candidates.append(body.get("mid"))
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return ""

    def _manager_user_ids(self) -> List[str]:
        records = self.directory_service.list_employees()
        manager_ids = {
            str(record.manager_user_id or "").strip()
            for record in records
            if str(record.manager_user_id or "").strip() and record.is_active
        }
        if manager_ids:
            return sorted(manager_ids)
        local_records = self.employee_repository.list_recent(limit=5000)
        return sorted({
            str(getattr(record, "manager_user_id", "") or "").strip()
            for record in local_records
            if str(getattr(record, "manager_user_id", "") or "").strip() and bool(getattr(record, "is_active", False))
        })

    def list_active_subordinates(self, manager_user_id: str) -> List[OfficeSealEmployee]:
        records = self.directory_service.get_by_manager_user_id(manager_user_id)
        employees = [self._employee_from_google(record) for record in records if record.is_active]
        if employees:
            return [employee for employee in employees if employee is not None]
        local_records = self.employee_repository.get_by_manager_user_id(manager_user_id)
        return [
            OfficeSealEmployee(
                employee_id=str(getattr(record, "employee_user_id", "") or "").strip(),
                user_id=str(getattr(record, "employee_user_id", "") or "").strip(),
                name=str(getattr(record, "employee_name", "") or "").strip(),
                manager_user_id=str(getattr(record, "manager_user_id", "") or "").strip(),
                office=str(getattr(record, "office", "") or "").strip(),
                is_active=bool(getattr(record, "is_active", False)),
                gender=self._gender_from_name(str(getattr(record, "employee_name", "") or "")),
            )
            for record in local_records
            if bool(getattr(record, "is_active", False))
        ]

    def _all_active_employees(self) -> List[OfficeSealEmployee]:
        records = self.directory_service.list_employees()
        employees = [self._employee_from_google(record) for record in records if record.is_active]
        employees = [employee for employee in employees if employee is not None]
        if employees:
            return employees
        local_records = self.employee_repository.list_recent(limit=5000)
        return [
            OfficeSealEmployee(
                employee_id=str(getattr(record, "employee_user_id", "") or "").strip(),
                user_id=str(getattr(record, "employee_user_id", "") or "").strip(),
                name=str(getattr(record, "employee_name", "") or "").strip(),
                manager_user_id=str(getattr(record, "manager_user_id", "") or "").strip(),
                office=str(getattr(record, "office", "") or "").strip(),
                is_active=bool(getattr(record, "is_active", False)),
                gender=self._gender_from_name(str(getattr(record, "employee_name", "") or "")),
            )
            for record in local_records
            if bool(getattr(record, "is_active", False))
        ]

    def list_active_office_mates(self, office: str) -> List[OfficeSealEmployee]:
        office_value = self._normalize_office(office)
        if not office_value:
            return []
        records = self.directory_service.list_employees()
        employees = [
            self._employee_from_google(record)
            for record in records
            if record.is_active and self._normalize_office(record.office) == office_value
        ]
        employees = [employee for employee in employees if employee is not None]
        if employees:
            return employees
        local_records = self.employee_repository.list_recent(limit=5000)
        return [
            OfficeSealEmployee(
                employee_id=str(getattr(record, "employee_user_id", "") or "").strip(),
                user_id=str(getattr(record, "employee_user_id", "") or "").strip(),
                name=str(getattr(record, "employee_name", "") or "").strip(),
                manager_user_id=str(getattr(record, "manager_user_id", "") or "").strip(),
                office=str(getattr(record, "office", "") or "").strip(),
                is_active=bool(getattr(record, "is_active", False)),
            )
            for record in local_records
            if bool(getattr(record, "is_active", False))
            and self._normalize_office(str(getattr(record, "office", "") or "")) == office_value
        ]

    def _notify_office_mates(self, sealed_by: OfficeSealEmployee, date: str, photo_url: str = "") -> None:
        for employee in self.list_active_office_mates(sealed_by.office):
            if not employee.user_id or employee.user_id == sealed_by.user_id:
                continue
            text = (
                "Кабинет №{office} уже опломбирован сегодня.\n\n"
                "Кто отметил: {sealed_by}\n"
                "Дата: {date}"
            ).format(
                office=sealed_by.office,
                sealed_by=sealed_by.name or sealed_by.user_id,
                date=date,
            )
            if photo_url:
                text += "\nФото: {photo}".format(photo=photo_url)
            try:
                self.max_client.send_message(user_id=int(employee.user_id), text=text, buttons=[])
            except ValueError:
                try:
                    self.max_client.send_message(user_id=employee.user_id, text=text, buttons=[])
                except Exception:
                    continue
            except Exception:
                continue

    def _office_journal_row(self, date: str, office: str) -> OfficeSealJournalRow | None:
        office_value = self._normalize_office(office)
        for row in self.journal_service.list_rows():
            if row.date == date and self._normalize_office(row.office) == office_value:
                return row
        return None

    @staticmethod
    def _office_exception_text(office: str, exception: OfficeSealException) -> str:
        suffix = ""
        if exception.reason:
            suffix = " Причина: {reason}.".format(reason=exception.reason)
        return "Кабинет №{office} сегодня в исключениях, опломбирование не требуется.{suffix}".format(
            office=office,
            suffix=suffix,
        )

    @classmethod
    def _group_employees_by_office(cls, employees: Iterable[OfficeSealEmployee]) -> dict[str, List[OfficeSealEmployee]]:
        result: dict[str, List[OfficeSealEmployee]] = {}
        labels: dict[str, str] = {}
        for employee in employees:
            key = cls._normalize_office(employee.office)
            if not key:
                continue
            labels.setdefault(key, employee.office)
            result.setdefault(labels[key], []).append(employee)
        return result

    def get_employee_by_user_id(self, user_id: str) -> OfficeSealEmployee | None:
        record = self.directory_service.get_by_user_id(user_id)
        employee = self._employee_from_google(record) if record is not None else None
        if employee is not None:
            return employee
        local = self.employee_repository.get_by_user_id(user_id)
        if local is None:
            return None
        local_user_id = str(getattr(local, "employee_user_id", "") or "").strip()
        return OfficeSealEmployee(
            employee_id=local_user_id or str(user_id),
            user_id=local_user_id or str(user_id),
            name=str(getattr(local, "employee_name", "") or "").strip(),
            manager_user_id=str(getattr(local, "manager_user_id", "") or "").strip(),
            office=str(getattr(local, "office", "") or "").strip(),
            is_active=bool(getattr(local, "is_active", False)),
            gender=self._gender_from_name(str(getattr(local, "employee_name", "") or "")),
        )

    def _first_photo_attachment(self, attachments: Iterable[MaxAttachment], *, message_id: str = "") -> MaxAttachment | None:
        for attachment in attachments:
            if self._is_photo_attachment(attachment):
                return attachment
        if not message_id:
            return None
        try:
            message = self.max_client.get_message(message_id)
        except Exception:
            return None
        body = message.get("body") if isinstance(message, dict) else None
        raw_attachments = body.get("attachments") if isinstance(body, dict) else []
        for item in raw_attachments or []:
            try:
                attachment = MaxAttachment.model_validate(item)
            except Exception:
                continue
            if self._is_photo_attachment(attachment):
                return attachment
        return None

    @staticmethod
    def _normalize_office(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip()).lower()

    @staticmethod
    def _is_photo_attachment(attachment: MaxAttachment) -> bool:
        attachment_type = str(attachment.type or "").lower()
        filename = str(attachment.filename or "").lower()
        payload = attachment.payload
        has_url = bool(payload and payload.url)
        return has_url and (
            attachment_type in {"image", "photo"}
            or filename.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))
        )

    def _save_photo_and_build_url(self, attachment: MaxAttachment) -> str:
        if not attachment.payload or not attachment.payload.url:
            raise ValueError("photo attachment has no url")
        self.photo_dir.mkdir(parents=True, exist_ok=True)
        content, content_type = self._download_photo(attachment.payload.url)
        extension = self._photo_extension(attachment.filename or "", content_type)
        token = uuid4().hex
        path = self.photo_dir / f"{token}{extension}"
        path.write_bytes(content)
        return "{base}/api/office-seal/photos/{name}".format(
            base=self.public_base_url,
            name=path.name,
        )

    @staticmethod
    def _download_photo(url: str) -> tuple[bytes, str]:
        request = Request(url=url, headers={"User-Agent": "skud/0.1.0"})
        with urlopen(request, timeout=60) as response:
            content_type = response.headers.get("Content-Type", "")
            return response.read(), content_type

    @staticmethod
    def _photo_extension(filename: str, content_type: str) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            return ".jpg" if suffix == ".jpeg" else suffix
        return PHOTO_EXTENSIONS.get(content_type.split(";", 1)[0].strip().lower(), ".jpg")

    def _employee_from_google(self, record: GoogleSheetsEmployeeRecord | None) -> OfficeSealEmployee | None:
        if record is None:
            return None
        employee_user_id = str(record.employee_user_id or "").strip()
        employee_id = str(record.employee_id or "").strip() or employee_user_id
        if not employee_user_id and not employee_id:
            return None
        return OfficeSealEmployee(
            employee_id=employee_id,
            user_id=employee_user_id,
            name=str(record.employee_name or "").strip(),
            manager_user_id=str(record.manager_user_id or "").strip(),
            office=str(record.office or "").strip(),
            is_active=bool(record.is_active),
            gender=self._gender_from_record(record),
        )

    @staticmethod
    def _gender_from_record(record: GoogleSheetsEmployeeRecord) -> str:
        schedule = f"{record.schedule_name} {record.schedule_id}".lower()
        if "девуш" in schedule or "жен" in schedule:
            return "female"
        if "парн" in schedule or "муж" in schedule:
            return "male"
        return OfficeSealingService._gender_from_name(str(record.employee_name or ""))

    @staticmethod
    def _gender_from_name(name: str) -> str:
        parts = str(name or "").strip().split()
        if len(parts) >= 3 and parts[2].lower().endswith("вна"):
            return "female"
        return "male"

    def _now(self, now: datetime | None) -> datetime:
        if now is None:
            return datetime.now(ZoneInfo(self.timezone_name))
        if now.tzinfo is None:
            return now.replace(tzinfo=ZoneInfo(self.timezone_name))
        return now.astimezone(ZoneInfo(self.timezone_name))

    @staticmethod
    def _is_workday(value: datetime) -> bool:
        return value.weekday() < 5

    def _is_in_window(self, value: datetime) -> bool:
        current = value.time().replace(second=0, microsecond=0)
        return self.window_start <= current <= self.window_end

    @staticmethod
    def _parse_time(value: str, fallback: time) -> time:
        match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(value or ""))
        if not match:
            return fallback
        hours = int(match.group(1))
        minutes = int(match.group(2))
        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
            return fallback
        return time(hours, minutes)

    @staticmethod
    def _normalize_public_base_url(value: str) -> str:
        base = str(value or "").strip().rstrip("/")
        if base.endswith("/api/webhooks/max"):
            base = base[: -len("/api/webhooks/max")]
        return base or "http://localhost:8000"
