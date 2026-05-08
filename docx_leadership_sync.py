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
STRUCTURE_SHEET_TITLE = "DOCX_Структура"
TOP_MANAGER_NAME = "Посунько Руслан Юрьевич"
DIRECT_DEPUTIES = {
    "Слабенко Александр Владимирович",
    "Кудрявцева Марина Алексеевна",
    "Корсикова Ариадна Юрьевна",
    "Комаровский Андрей Петрович",
    "Кузьменко Елена Викторовна",
    "Маркова Елена Борисовна",
    "Сафонова Светлана Вячеславовна",
}

# Explicit hierarchy from the DOCX structure review.
MANAGER_OVERRIDES = {
    TOP_MANAGER_NAME: "",
    "Слабенко Александр Владимирович": TOP_MANAGER_NAME,
    "Кудрявцева Марина Алексеевна": TOP_MANAGER_NAME,
    "Корсикова Ариадна Юрьевна": TOP_MANAGER_NAME,
    "Комаровский Андрей Петрович": TOP_MANAGER_NAME,
    "Кузьменко Елена Викторовна": TOP_MANAGER_NAME,
    "Маркова Елена Борисовна": TOP_MANAGER_NAME,
    "Сафонова Светлана Вячеславовна": TOP_MANAGER_NAME,
    "Антипина Луиза Николаевна": "Слабенко Александр Владимирович",
    "Назаров Дмитрий Алишерович": "Слабенко Александр Владимирович",
    "Клоченок Анастасия Ивановна": "Кудрявцева Марина Алексеевна",
    "Марникова Наталья Евгеньевна": "Кудрявцева Марина Алексеевна",
    "Ковалкина Алена Александровна": "Корсикова Ариадна Юрьевна",
    "Сафонов Алексей Валентинович": "Сафонова Светлана Вячеславовна",
    "Филимоненко Виктория Викторовна": "Сафонов Алексей Валентинович",
    "Соколова Елена Юрьевна": "Сафонов Алексей Валентинович",
    "Дидович Елена Феодосеевна": "Сафонов Алексей Валентинович",
    "Колеватых Наталья Николаевна": "Сафонов Алексей Валентинович",
    "Баженов Станислав Сергеевич": "Марникова Наталья Евгеньевна",
    "Молчанова Яна Геннадьевна": "Корсикова Ариадна Юрьевна",
    "Лебедев Александр Иванович": "Молчанова Яна Геннадьевна",
    "Огнева Анна Алексеевна": "Молчанова Яна Геннадьевна",
    "Кондакова Юлия Борисовна": "Лебедев Александр Иванович",
    "Носко Кирилл Геннадьевич": "Кондакова Юлия Борисовна",
    "Волкова Эвелина Викторовна": "Кондакова Юлия Борисовна",
    "Толкачева Татьяна Александровна": "Кондакова Юлия Борисовна",
    "Кузьмина Надежда Юрьевна": "Кондакова Юлия Борисовна",
    "Кислицын Максим Анатольевич": "Носко Кирилл Геннадьевич",
    "Канева Валерия Игоревна": "Кислицын Максим Анатольевич",
}

DEPARTMENT_OVERRIDES = {
    "Антипина Луиза Николаевна": "8-ОРиУН",
    "Назаров Дмитрий Алишерович": "18-ООК",
    "Клоченок Анастасия Ивановна": "3-ООО",
    "Марникова Наталья Евгеньевна": "22-ПО№1",
}

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


@dataclass(frozen=True)
class StructureNode:
    kind: str
    text: str
    x: int
    y: int


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
    structure_index: Dict[str, StructureNode],
    department_nodes: List[StructureNode],
) -> List[EmployeeCellUpdate]:
    updates: List[EmployeeCellUpdate] = []
    for row in rows:
        employee = employee_index.get(row.employee_name)
        if employee is None:
            continue
        manager_name = resolve_manager_name(row)
        department_name = resolve_department_name(row, structure_index, department_nodes)
        if department_name:
            updates.append(EmployeeCellUpdate(employee.row_number, "G", department_name))
        if manager_name:
            updates.append(EmployeeCellUpdate(employee.row_number, "E", manager_name))
    return updates


def build_normalized_rows(
    rows: Iterable[LeadershipTemplateRow],
    employee_index: Dict[str, EmployeeSheetRow],
    structure_index: Dict[str, StructureNode],
    department_nodes: List[StructureNode],
) -> List[List[str]]:
    normalized_rows: List[List[str]] = []
    for index, row in enumerate(rows, start=1):
        employee = employee_index.get(row.employee_name)
        status = "Готово"
        manager_name = resolve_manager_name(row)
        top_manager_name = resolve_top_manager_name(row)
        department_name = resolve_department_name(row, structure_index, department_nodes)
        if employee is None:
            status = "Не найден в Сотрудники"
        elif row.employee_name == TOP_MANAGER_NAME:
            status = "Топ-уровень"
            manager_name = ""
        elif not manager_name:
            status = "Требует_проверки"
        normalized_rows.append(
            [
                str(index),
                row.employee_name,
                employee.employee_user_id if employee else "",
                department_name,
                manager_name,
                "",
                row.replacement_name,
                top_manager_name,
                row.comment,
                status,
            ]
        )
    return normalized_rows


def resolve_manager_name(row: LeadershipTemplateRow) -> str:
    return normalize_text(MANAGER_OVERRIDES.get(row.employee_name, row.manager_name))


def resolve_top_manager_name(row: LeadershipTemplateRow) -> str:
    if row.employee_name == TOP_MANAGER_NAME:
        return TOP_MANAGER_NAME
    return TOP_MANAGER_NAME


def resolve_department_name(
    row: LeadershipTemplateRow,
    structure_index: Dict[str, StructureNode],
    department_nodes: List[StructureNode],
) -> str:
    explicit_department = normalize_text(DEPARTMENT_OVERRIDES.get(row.employee_name, row.department_name))
    if explicit_department:
        return explicit_department

    employee_node = structure_index.get(row.employee_name)
    if employee_node is None or not department_nodes:
        return ""

    candidates = [node for node in department_nodes if node.y > employee_node.y]
    if not candidates:
        candidates = department_nodes

    def score(node: StructureNode) -> tuple[int, int, int]:
        vertical = max(node.y - employee_node.y, 0)
        horizontal = abs(node.x - employee_node.x)
        return (vertical, horizontal, node.y)

    best = min(candidates, key=score)
    return normalize_text(best.text)


def get_cell(row: List[str], header_index: Dict[str, int], header_name: str) -> str:
    idx = header_index.get(header_name)
    if idx is None or idx >= len(row):
        return ""
    return normalize_text(row[idx])


def build_structure_index(values: List[List[str]]) -> tuple[Dict[str, StructureNode], List[StructureNode]]:
    if not values:
        return {}, []

    headers = [normalize_text(cell) for cell in values[0]]
    index = {name: idx for idx, name in enumerate(headers) if name}
    nodes: Dict[str, StructureNode] = {}
    department_nodes: List[StructureNode] = []

    for raw_row in values[1:]:
        kind = get_cell(raw_row, index, "Тип")
        text = get_cell(raw_row, index, "Текст")
        x = get_cell(raw_row, index, "X")
        y = get_cell(raw_row, index, "Y")
        if not kind or not text:
            continue
        if not x.lstrip("-").isdigit() or not y.lstrip("-").isdigit():
            continue
        node = StructureNode(kind=kind, text=text, x=int(x), y=int(y))
        if kind == "ФИО" and text not in nodes:
            nodes[text] = node
        elif kind == "Код_подразделения":
            department_nodes.append(node)
    return nodes, department_nodes


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
    structure_values = sheets_service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{STRUCTURE_SHEET_TITLE}!A:E",
    ).execute().get("values", [])

    template_rows = parse_template_rows(template_values)
    employee_index = build_employee_index(employee_values)
    structure_index, department_nodes = build_structure_index(structure_values)

    employee_updates = build_employee_updates(template_rows, employee_index, structure_index, department_nodes)
    normalized_rows = build_normalized_rows(template_rows, employee_index, structure_index, department_nodes)

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
