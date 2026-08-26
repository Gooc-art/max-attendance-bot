from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.services.office_sealing import (
    OFFICE_SEAL_EXCEPTION_HEADERS,
    OFFICE_SEAL_JOURNAL_HEADERS,
    OFFICE_SEAL_REMINDER_UNSUBSCRIBE_HEADERS,
    OfficeSealJournalService,
)


def _column_letter(index: int) -> str:
    result = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _build_sheets_service(service_account_file: str):
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credentials = service_account.Credentials.from_service_account_file(
        service_account_file,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def ensure_employee_office_column(sheets_service, spreadsheet_id: str) -> str:
    values = (
        sheets_service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range="Сотрудники!1:1")
        .execute()
        .get("values", [])
    )
    headers = [str(item).strip() for item in values[0]] if values else []
    if "Кабинет" in headers:
        return "exists"
    column = _column_letter(len(headers) + 1)
    (
        sheets_service.spreadsheets()
        .values()
        .update(
            spreadsheetId=spreadsheet_id,
            range=f"Сотрудники!{column}1",
            valueInputOption="USER_ENTERED",
            body={"values": [["Кабинет"]]},
        )
        .execute()
    )
    return f"added:{column}"


def main() -> None:
    settings = get_settings()
    if not settings.google_sheets_spreadsheet_id:
        raise SystemExit("GOOGLE_SHEETS_SPREADSHEET_ID is empty")
    if not settings.google_service_account_file or not Path(settings.google_service_account_file).exists():
        raise SystemExit("GOOGLE_SERVICE_ACCOUNT_FILE is missing")

    sheets_service = _build_sheets_service(settings.google_service_account_file)
    office_column_status = ensure_employee_office_column(sheets_service, settings.google_sheets_spreadsheet_id)

    journal = OfficeSealJournalService(
        spreadsheet_id=settings.google_sheets_spreadsheet_id,
        service_account_file=settings.google_service_account_file,
    )
    journal.ensure_sheet()
    journal.ensure_exception_sheet()
    journal.ensure_reminder_unsubscribe_sheet()
    print(f"employee office column: {office_column_status}")
    print(f"journal headers: {', '.join(OFFICE_SEAL_JOURNAL_HEADERS)}")
    print(f"office exception headers: {', '.join(OFFICE_SEAL_EXCEPTION_HEADERS)}")
    print(f"office reminder unsubscribe headers: {', '.join(OFFICE_SEAL_REMINDER_UNSUBSCRIBE_HEADERS)}")


if __name__ == "__main__":
    main()
