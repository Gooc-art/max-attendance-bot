from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional


PROJECT_TITLE = "Контроль_опозданий_MAX"
SERVICE_ACCOUNT_FILE = Path("/Users/goocbk.ru/secure/attendance-max-bot-service-account.json")
SPREADSHEET_ID = "1tg5umqy7-72LMLEaXu6n29OvGDSpkOE_adw_7PxsP54"
TEMPLATE_SHEET_TITLE = "DOCX_Связи_ШАБЛОН"
NORMALIZED_SHEET_TITLE = "DOCX_Связи_НОРМА"
EMPLOYEE_SHEET_TITLE = "Сотрудники"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

TEMPLATE_HEADERS = [
    "№",
    "ФИО",
    "Подразделение",
    "ФИО_руководителя",
    "ФИО_замещающего",
    "ФИО_топ_руководителя",
    "Комментарий",
]

NORMALIZED_HEADERS = [
    "№",
    "ФИО_сотрудника",
    "employee_user_id",
    "Подразделение",
    "ФИО_руководителя",
    "manager_user_id",
    "ФИО_замещающего",
    "ФИО_топ_руководителя",
    "Комментарий",
    "Статус",
]


@dataclass(frozen=True)
class LeadershipTemplateRow:
    employee_name: str
    department_name: str = ""
    manager_name: str = ""
    replacement_name: str = ""
    top_manager_name: str = ""
    comment: str = ""


@dataclass(frozen=True)
class EmployeeSheetRow:
    row_number: int
    employee_name: str
    employee_user_id: str


@dataclass(frozen=True)
class EmployeeCellUpdate:
    row_number: int
    column: str
    value: str


def normalize_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def parse_template_rows(values: List[List[str]]) -> List[LeadershipTemplateRow]:
    if not values:
        return []

    headers = [normalize_text(cell) for cell in values[0]]
    index = {name: idx for idx, name in enumerate(headers) if name}
    rows: List[LeadershipTemplateRow] = []

    for raw_row in values[1:]:
        employee_name = get_cell(raw_row, index, "ФИО")
        if not employee_name:
            continue
        rows.append(
            LeadershipTemplateRow(
                employee_name=employee_name,
                department_name=get_cell(raw_row, index, "Подразделение"),
                manager_name=get_cell(raw_row, index, "ФИО_руководителя"),
                replacement_name=get_cell(raw_row, index, "ФИО_замещающего"),
                top_manager_name=get_cell(raw_row, index, "ФИО_топ_руководителя"),
                comment=get_cell(raw_row, index, "Комментарий"),
            )
        )
    return rows


def build_employee_index(values: List[List[str]]) -> Dict[str, EmployeeSheetRow]:
    if not values:
        return {}

    headers = [normalize_text(cell) for cell in values[0]]
    index = {name: idx for idx, name in enumerate(headers) if name}
    result: Dict[str, EmployeeSheetRow] = {}

    for row_number, raw_row in enumerate(values[1:], start=2):
        employee_name = get_cell(raw_row, index, "ФИО")
        employee_user_id = get_cell(raw_row, index, "ID_пользователя_MAX")
        if not employee_name:
            continue
        result[employee_name] = EmployeeSheetRow(
            row_number=row_number,
            employee_name=employee_name,
            employee_user_id=employee_user_id,
        )
    return result


def build_employee_updates(
    rows: Iterable[LeadershipTemplateRow],
    employee_index: Dict[str, EmployeeSheetRow],
) -> List[EmployeeCellUpdate]:
    updates: List[EmployeeCellUpdate] = []
    for row in rows:
        employee = employee_index.get(row.employee_name)
        if employee is None:
            continue
        if row.department_name:
            updates.append(EmployeeCellUpdate(employee.row_number, "G", row.department_name))
        if row.manager_name:
            updates.append(EmployeeCellUpdate(employee.row_number, "E", row.manager_name))
    return updates


def build_normalized_rows(
    rows: Iterable[LeadershipTemplateRow],
    employee_index: Dict[str, EmployeeSheetRow],
) -> List[List[str]]:
    normalized_rows: List[List[str]] = []
    for index, row in enumerate(rows, start=1):
        employee = employee_index.get(row.employee_name)
        status = "Готово"
        top_manager_name = row.top_manager_name
        if employee is None:
            status = "Не найден в Сотрудники"
        elif not row.manager_name:
            status = "Топ-уровень"
            top_manager_name = row.employee_name
        elif not row.top_manager_name:
            top_manager_name = row.manager_name
        normalized_rows.append(
            [
                str(index),
                row.employee_name,
                employee.employee_user_id if employee else "",
                row.department_name,
                row.manager_name,
                "",
                row.replacement_name,
                top_manager_name,
                row.comment,
                status,
            ]
        )
    return normalized_rows


def get_cell(row: List[str], header_index: Dict[str, int], header_name: str) -> str:
    idx = header_index.get(header_name)
    if idx is None or idx >= len(row):
        return ""
    return normalize_text(row[idx])


def load_credentials():
    from google.oauth2 import service_account

    if not SERVICE_ACCOUNT_FILE.exists():
        raise FileNotFoundError(f"Не найден файл ключа: {SERVICE_ACCOUNT_FILE}")
    return service_account.Credentials.from_service_account_file(
        str(SERVICE_ACCOUNT_FILE),
        scopes=SCOPES,
    )


def create_services():
    from googleapiclient.discovery import build

    creds = load_credentials()
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def ensure_sheet(sheets_service, sheet_title: str) -> None:
    meta = sheets_service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    existing = {
        sheet["properties"]["title"]: sheet["properties"]["sheetId"]
        for sheet in meta.get("sheets", [])
    }
    if sheet_title in existing:
        return
    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": [{"addSheet": {"properties": {"title": sheet_title, "index": len(existing)}}}]},
    ).execute()


def clear_and_write_rows(sheets_service, sheet_title: str, headers: List[str], rows: List[List[str]]) -> None:
    sheets_service.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{sheet_title}!A:Z",
    ).execute()
    sheets_service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{sheet_title}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [headers, *rows]},
    ).execute()


def apply_employee_updates(sheets_service, updates: List[EmployeeCellUpdate]) -> int:
    if not updates:
        return 0

    data = [
        {
            "range": f"{EMPLOYEE_SHEET_TITLE}!{update.column}{update.row_number}",
            "majorDimension": "ROWS",
            "values": [[update.value]],
        }
        for update in updates
    ]
    sheets_service.spreadsheets().values().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={
            "valueInputOption": "USER_ENTERED",
            "data": data,
        },
    ).execute()
    return len(updates)


def sync_leadership_template() -> dict[str, int]:
    sheets_service = create_services()

    template_values = sheets_service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{TEMPLATE_SHEET_TITLE}!A:G",
    ).execute().get("values", [])
    employee_values = sheets_service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{EMPLOYEE_SHEET_TITLE}!A:Q",
    ).execute().get("values", [])

    template_rows = parse_template_rows(template_values)
    employee_index = build_employee_index(employee_values)

    employee_updates = build_employee_updates(template_rows, employee_index)
    normalized_rows = build_normalized_rows(template_rows, employee_index)

    ensure_sheet(sheets_service, NORMALIZED_SHEET_TITLE)
    clear_and_write_rows(sheets_service, NORMALIZED_SHEET_TITLE, NORMALIZED_HEADERS, normalized_rows)
    written_updates = apply_employee_updates(sheets_service, employee_updates)

    return {
        "template_rows": len(template_rows),
        "normalized_rows": len(normalized_rows),
        "employee_updates": written_updates,
    }


def main() -> None:
    result = sync_leadership_template()
    print("Синхронизация шаблона руководителей завершена:")
    print(f"Строк из шаблона: {result['template_rows']}")
    print(f"Строк в нормализованной вкладке: {result['normalized_rows']}")
    print(f"Обновлено строк сотрудников: {result['employee_updates']}")


if __name__ == "__main__":
    main()
