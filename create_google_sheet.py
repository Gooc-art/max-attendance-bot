from __future__ import annotations

import json
from pathlib import Path

PROJECT_TITLE = "Контроль_опозданий_MAX"
SERVICE_ACCOUNT_FILE = Path("/Users/goocbk.ru/secure/attendance-max-bot-service-account.json")
FOLDER_ID = "1kAJrAbR9ehmGLNwblRuMgZxrYRWR4C9w"
EXISTING_SPREADSHEET_ID = "1tg5umqy7-72LMLEaXu6n29OvGDSpkOE_adw_7PxsP54"
STAFF_CATALOG_FILE = Path("/Users/goocbk.ru/skud/data/staff_catalog.json")
STAFF_BINDINGS_FILE = Path("/Users/goocbk.ru/skud/data/staff_bindings.json")
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


SHEET_TITLES = [
    "Сотрудники",
    "Подразделения",
    "Графики",
    "Исключения",
    "Связи_руководства",
    "Замещения",
    "Правила",
    "Журнал",
    "Исключения_кабинетов",
    "Справочники",
]


HEADERS = {
    "Сотрудники": [
        "ID_сотрудника",
        "ФИО",
        "ФИО_для_сопоставления",
        "ID_пользователя_MAX",
        "ФИО_руководителя",
        "ID_руководителя",
        "Подразделение",
        "ID_подразделения",
        "Роль",
        "График",
        "ID_графика",
        "Формат_работы",
        "Допуск_опоздания_мин",
        "Работает",
        "Дата_приема",
        "Дата_увольнения",
        "Комментарий",
        "Кабинет",
    ],
    "Подразделения": [
        "ID_подразделения",
        "Наименование_подразделения",
        "Родительское_подразделение",
        "ID_родительского_подразделения",
        "ФИО_руководителя",
        "ID_руководителя",
        "Активно",
        "Комментарий",
    ],
    "Графики": [
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
    "Исключения": [
        "ID_исключения",
        "ФИО",
        "ID_сотрудника",
        "Дата_начала",
        "Дата_окончания",
        "Тип_исключения",
        "Статус_согласования",
        "ФИО_согласовавшего",
        "ID_согласовавшего",
        "Источник",
        "Комментарий",
    ],
    "Связи_руководства": [
        "ID_связи",
        "ID_сотрудника",
        "ФИО_сотрудника",
        "ID_руководителя",
        "ФИО_руководителя",
        "Тип_руководителя",
        "Основной",
        "Дата_начала",
        "Дата_окончания",
        "Приоритет",
        "Комментарий",
    ],
    "Замещения": [
        "ID_замещения",
        "ID_основного_руководителя",
        "ФИО_основного_руководителя",
        "ID_замещающего",
        "ФИО_замещающего",
        "Причина",
        "Дата_начала",
        "Дата_окончания",
        "Распространяется_на_согласование",
        "Распространяется_на_отчеты",
        "Активно",
        "Комментарий",
    ],
    "Правила": [
        "Параметр",
        "Значение",
        "Комментарий",
    ],
    "Журнал": [
        "Дата",
        "Время",
        "ID_сотрудника",
        "Кабинет",
        "Ссылка_на_фото",
    ],
    "Исключения_кабинетов": [
        "Кабинет",
        "Дата_начала",
        "Дата_окончания",
        "Причина",
        "Активно",
        "Комментарий",
    ],
}


RULES_ROWS = [
    ["Минут_допуска_по_умолчанию", "10", "Если у сотрудника не указан личный допуск"],
    ["Считать_неявкой_после", "12:00", "Если до этого времени нет входа"],
    ["Срок_ответа_сотрудника", "1_рабочий_день", "Сколько времени дается на ответ"],
    ["Часовой_пояс", "Europe/Moscow", "Использовать единый часовой пояс"],
    ["Формат_даты", "YYYY-MM-DD", "Единый формат даты"],
    ["Формат_времени", "HH:MM", "Единый формат времени"],
]


SCHEDULE_ROWS = [
    ["ГР001", "Пятидневка 09:00", "09:00", "18:00", "09:00", "18:00", "09:00", "18:00", "09:00", "18:00", "09:00", "18:00", "", "", "", "", 10, "13:00", "14:00", 60, 480, "fixed", "Да", "Основной график"],
    ["ГР002", "Сменный график", "08:00", "20:00", "08:00", "20:00", "20:00", "08:00", "20:00", "08:00", "08:00", "20:00", "08:00", "20:00", "", "", 5, "13:00", "14:00", 60, 660, "fixed", "Да", "Пример сменного графика"],
    ["ГР003", "Пятидневка - Девушки 08:30-12:30 / 14:00-17:15", "08:30", "17:15", "08:30", "17:15", "08:30", "17:15", "08:30", "17:15", "08:30", "17:15", "", "", "", "", 10, "12:30", "14:00", 90, 429, "fixed", "Да", "Обед 12:30-14:00"],
    ["ГР004", "Пятидневка - Парни 08:30-12:30 / 14:00-18:15", "08:30", "18:15", "08:30", "18:15", "08:30", "18:15", "08:30", "18:15", "08:30", "18:15", "", "", "", "", 10, "12:30", "14:00", 90, 480, "fixed", "Да", "Обед 12:30-14:00"],
]


REFERENCE_COLUMNS = {
    "A": ["Роли", "Сотрудник", "Руководитель", "Безопасность", "HR", "Администратор", "Топ_руководитель"],
    "B": ["Формат_работы", "Офис", "Удаленно", "Гибрид", "Сменный"],
    "C": ["Да_Нет", "Да", "Нет"],
    "D": ["Тип_исключения", "Отпуск", "Больничный", "Командировка", "Удаленная_работа", "Разрешенное_опоздание", "Отгул", "Неявка_по_уважительной_причине"],
    "E": ["Статус_согласования", "На_согласовании", "Согласовано", "Отклонено"],
    "F": ["Источник", "HR", "Бот", "Ручной_ввод", "Импорт"],
    "G": ["Тип_руководителя", "Непосредственный_руководитель", "Руководитель_отдела", "Курирующий_зам", "Главный_руководитель"],
    "H": ["Причина_замещения", "Отпуск", "Больничный", "Командировка", "Иное"],
}


COLUMN_WIDTHS = {
    "Сотрудники": {
        0: 120,
        1: 260,
        2: 260,
        3: 220,
        4: 240,
        5: 140,
        6: 220,
        7: 140,
        8: 140,
        9: 180,
        10: 120,
        11: 160,
        12: 140,
        13: 110,
        14: 120,
        15: 120,
        16: 240,
        17: 120,
    },
    "Подразделения": {
        0: 140,
        1: 260,
        2: 240,
        3: 170,
        4: 240,
        5: 140,
        6: 110,
        7: 240,
    },
    "Графики": {
        0: 120,
        1: 220,
        2: 130,
        3: 130,
        4: 130,
        5: 130,
        6: 130,
        7: 130,
        8: 130,
        9: 130,
        10: 130,
        11: 130,
        12: 130,
        13: 130,
        14: 130,
        15: 130,
        16: 170,
        17: 120,
        18: 120,
        19: 120,
        20: 150,
        21: 130,
        22: 110,
        23: 220,
    },
    "Исключения": {
        0: 130,
        1: 260,
        2: 130,
        3: 120,
        4: 120,
        5: 220,
        6: 180,
        7: 240,
        8: 160,
        9: 140,
        10: 240,
    },
    "Связи_руководства": {
        0: 120,
        1: 130,
        2: 240,
        3: 140,
        4: 240,
        5: 220,
        6: 110,
        7: 120,
        8: 120,
        9: 100,
        10: 240,
    },
    "Замещения": {
        0: 130,
        1: 180,
        2: 240,
        3: 160,
        4: 240,
        5: 160,
        6: 120,
        7: 120,
        8: 230,
        9: 180,
        10: 110,
        11: 240,
    },
    "Правила": {
        0: 220,
        1: 180,
        2: 320,
    },
    "Журнал": {
        0: 120,
        1: 100,
        2: 180,
        3: 120,
        4: 360,
    },
    "Исключения_кабинетов": {
        0: 120,
        1: 120,
        2: 120,
        3: 220,
        4: 100,
        5: 260,
    },
    "Справочники": {
        0: 220,
        1: 220,
        2: 160,
        3: 260,
        4: 220,
        5: 180,
        6: 220,
        7: 180,
    },
}


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
    sheets = build("sheets", "v4", credentials=creds)
    drive = build("drive", "v3", credentials=creds)
    return sheets, drive


def load_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def build_department_id_map(catalog: dict) -> dict[str, str]:
    departments = catalog.get("departments", {}) if isinstance(catalog, dict) else {}
    return {
        department_name: f"DEP{index:03d}"
        for index, department_name in enumerate(departments.keys(), start=1)
    }


def build_staff_rows(catalog: dict, bindings: dict) -> list[list[str]]:
    departments = catalog.get("departments", {}) if isinstance(catalog, dict) else {}
    binding_by_name = {
        str(binding.get("name", "")).strip(): binding
        for binding in bindings.values()
        if isinstance(binding, dict) and str(binding.get("name", "")).strip()
    }
    department_id_map = build_department_id_map(catalog)

    rows: list[list[str]] = []
    employee_index = 1
    for department_name, employee_names in departments.items():
        for employee_name in employee_names:
            binding = binding_by_name.get(employee_name, {})
            employee_user_id = str(binding.get("user_id", "")).strip()
            schedule_id = infer_schedule_id(employee_name)
            rows.append(
                [
                    f"EMP{employee_index:04d}",
                    employee_name,
                    employee_name,
                    employee_user_id,
                    "",
                    "",
                    department_name,
                    department_id_map.get(department_name, ""),
                    "Руководитель" if department_name == "0. Руководство" else "Сотрудник",
                    schedule_name_for(schedule_id),
                    schedule_id,
                    "Офис",
                    10,
                    "Да",
                    "",
                    "",
                    "",
                    "",
                ]
            )
            employee_index += 1
    return rows


def infer_schedule_id(employee_name: str) -> str:
    parts = [part for part in employee_name.split() if part]
    if len(parts) >= 3:
        patronymic = parts[2].lower()
        if patronymic.endswith(("овна", "евна", "ична")):
            return "ГР003"
        if patronymic.endswith(("ович", "евич", "ич")):
            return "ГР004"
    if len(parts) >= 2:
        first_name = parts[1].lower()
        if first_name.endswith(("а", "я", "ь")):
            return "ГР003"
    return "ГР004"


def schedule_name_for(schedule_id: str) -> str:
    mapping = {
        "ГР003": "Пятидневка - Девушки 08:30-12:30 / 14:00-17:15",
        "ГР004": "Пятидневка - Парни 08:30-12:30 / 14:00-18:15",
    }
    return mapping.get(schedule_id, "Пятидневка 09:00")


def build_department_rows(catalog: dict) -> list[list[str]]:
    departments = catalog.get("departments", {}) if isinstance(catalog, dict) else {}
    rows: list[list[str]] = []
    for index, department_name in enumerate(departments.keys(), start=1):
        rows.append(
            [
                f"DEP{index:03d}",
                department_name,
                "",
                "",
                "",
                "",
                "Да",
                "",
            ]
        )
    return rows


def create_spreadsheet(drive_service, sheets_service):
    file_metadata = {
        "name": PROJECT_TITLE,
        "mimeType": "application/vnd.google-apps.spreadsheet",
        "parents": [FOLDER_ID],
    }
    created_file = drive_service.files().create(
        body=file_metadata,
        fields="id, webViewLink",
        supportsAllDrives=True,
    ).execute()

    spreadsheet_id = created_file["id"]
    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "requests": [
                {
                    "updateSpreadsheetProperties": {
                        "properties": {
                            "title": PROJECT_TITLE,
                            "locale": "ru_RU",
                            "timeZone": "Europe/Moscow",
                        },
                        "fields": "title,locale,timeZone",
                    }
                }
            ]
        },
    ).execute()

    spreadsheet = sheets_service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="spreadsheetId,spreadsheetUrl,sheets(properties(sheetId,title))",
    ).execute()
    return spreadsheet


def get_existing_spreadsheet(sheets_service, spreadsheet_id):
    return sheets_service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="spreadsheetId,spreadsheetUrl,sheets(properties(sheetId,title))",
    ).execute()


def setup_sheets(sheets_service, spreadsheet_id, default_sheet_id):
    requests = [
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": default_sheet_id,
                    "title": SHEET_TITLES[0],
                    "index": 0,
                },
                "fields": "title,index",
            }
        }
    ]
    for index, title in enumerate(SHEET_TITLES[1:], start=1):
        requests.append(
            {
                "addSheet": {
                    "properties": {
                        "title": title,
                        "index": index,
                    }
                }
            }
        )

    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests},
    ).execute()


def get_sheet_map(sheets_service, spreadsheet_id):
    metadata = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    return {
        sheet["properties"]["title"]: sheet["properties"]["sheetId"]
        for sheet in metadata["sheets"]
    }


def ensure_missing_sheets(sheets_service, spreadsheet_id, sheet_map):
    requests = []
    existing_titles = set(sheet_map)
    for index, title in enumerate(SHEET_TITLES):
        if title not in existing_titles:
            requests.append(
                {
                    "addSheet": {
                        "properties": {
                            "title": title,
                            "index": index,
                        }
                    }
                }
            )

    if requests:
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests},
        ).execute()


def write_initial_values(sheets_service, spreadsheet_id):
    data = []

    for title in ["Сотрудники", "Подразделения", "Графики", "Исключения", "Связи_руководства", "Замещения", "Правила", "Журнал", "Исключения_кабинетов"]:
        rows = [HEADERS[title]]
        if title == "Графики":
            rows.extend(SCHEDULE_ROWS)
        elif title == "Правила":
            rows.extend(RULES_ROWS)
        data.append(
            {
                "range": f"{title}!A1",
                "majorDimension": "ROWS",
                "values": rows,
            }
        )

    for column, values in REFERENCE_COLUMNS.items():
        data.append(
            {
                "range": f"Справочники!{column}1",
                "majorDimension": "COLUMNS",
                "values": [values],
            }
        )

    sheets_service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "valueInputOption": "USER_ENTERED",
            "data": data,
        },
    ).execute()


def clear_range(sheets_service, spreadsheet_id, sheet_name: str, end_column: str) -> None:
    sheets_service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!A:{end_column}",
    ).execute()


def write_staff_data(sheets_service, spreadsheet_id):
    catalog = load_json_file(STAFF_CATALOG_FILE)
    bindings = load_json_file(STAFF_BINDINGS_FILE)
    if not catalog or not bindings:
        return {"catalog_rows": 0, "department_rows": 0}

    staff_rows = build_staff_rows(catalog, bindings)
    department_rows = build_department_rows(catalog)

    clear_range(sheets_service, spreadsheet_id, "Сотрудники", "R")
    clear_range(sheets_service, spreadsheet_id, "Подразделения", "H")

    sheets_service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "valueInputOption": "USER_ENTERED",
            "data": [
                {
                    "range": "Сотрудники!A1",
                    "majorDimension": "ROWS",
                    "values": [HEADERS["Сотрудники"], *staff_rows],
                },
                {
                    "range": "Подразделения!A1",
                    "majorDimension": "ROWS",
                    "values": [HEADERS["Подразделения"], *department_rows],
                },
            ],
        },
    ).execute()
    sync_employee_schedule_columns(sheets_service, spreadsheet_id)
    return {"catalog_rows": len(staff_rows), "department_rows": len(department_rows)}


def sync_employee_schedule_columns(sheets_service, spreadsheet_id):
    response = sheets_service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="Сотрудники!A1:R2000",
    ).execute()
    values = response.get("values", [])
    if len(values) <= 1:
        return

    schedule_rows = []
    for row in values[1:]:
        employee_name = row[1].strip() if len(row) > 1 else ""
        if not employee_name:
            schedule_rows.append(["", ""])
            continue
        schedule_id = infer_schedule_id(employee_name)
        schedule_rows.append([schedule_name_for(schedule_id), schedule_id])

    sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"Сотрудники!J2:K{len(schedule_rows) + 1}",
        valueInputOption="USER_ENTERED",
        body={"values": schedule_rows},
    ).execute()


def build_dropdown_request(sheet_id, start_row, end_row, column_index, values):
    return {
        "setDataValidation": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": start_row,
                "endRowIndex": end_row,
                "startColumnIndex": column_index,
                "endColumnIndex": column_index + 1,
            },
            "rule": {
                "condition": {
                    "type": "ONE_OF_LIST",
                    "values": [{"userEnteredValue": value} for value in values],
                },
                "strict": True,
                "showCustomUi": True,
            },
        }
    }


def format_sheets(sheets_service, spreadsheet_id, sheet_map):
    requests = []

    for title, sheet_id in sheet_map.items():
        header_values = HEADERS.get(title, [])
        column_count = len(header_values) if header_values else 6

        requests.extend(
            [
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": sheet_id,
                            "gridProperties": {"frozenRowCount": 1},
                        },
                        "fields": "gridProperties.frozenRowCount",
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": column_count,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {"red": 0.85, "green": 0.92, "blue": 0.97},
                                "textFormat": {"bold": True},
                                "wrapStrategy": "WRAP",
                                "verticalAlignment": "MIDDLE",
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColor,textFormat,wrapStrategy,verticalAlignment)",
                    }
                },
            ]
        )

        for column_index, width in COLUMN_WIDTHS.get(title, {}).items():
            requests.append(
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": column_index,
                            "endIndex": column_index + 1,
                        },
                        "properties": {"pixelSize": width},
                        "fields": "pixelSize",
                    }
                }
            )

    requests.append(
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_map["Справочники"],
                    "hidden": True,
                },
                "fields": "hidden",
            }
        }
    )

    employee_headers = HEADERS["Сотрудники"]
    department_headers = HEADERS["Подразделения"]
    schedule_headers = HEADERS["Графики"]
    exception_headers = HEADERS["Исключения"]
    management_headers = HEADERS["Связи_руководства"]
    substitution_headers = HEADERS["Замещения"]

    employee_sheet_id = sheet_map["Сотрудники"]
    department_sheet_id = sheet_map["Подразделения"]
    schedule_sheet_id = sheet_map["Графики"]
    exception_sheet_id = sheet_map["Исключения"]
    management_sheet_id = sheet_map["Связи_руководства"]
    substitution_sheet_id = sheet_map["Замещения"]

    requests.extend(
        [
            build_dropdown_request(employee_sheet_id, 1, 2000, employee_headers.index("Роль"), REFERENCE_COLUMNS["A"][1:]),
            build_dropdown_request(employee_sheet_id, 1, 2000, employee_headers.index("Формат_работы"), REFERENCE_COLUMNS["B"][1:]),
            build_dropdown_request(employee_sheet_id, 1, 2000, employee_headers.index("Работает"), REFERENCE_COLUMNS["C"][1:]),
            build_dropdown_request(department_sheet_id, 1, 2000, department_headers.index("Активно"), REFERENCE_COLUMNS["C"][1:]),
            build_dropdown_request(schedule_sheet_id, 1, 2000, schedule_headers.index("Активен"), REFERENCE_COLUMNS["C"][1:]),
            build_dropdown_request(exception_sheet_id, 1, 2000, exception_headers.index("Тип_исключения"), REFERENCE_COLUMNS["D"][1:]),
            build_dropdown_request(exception_sheet_id, 1, 2000, exception_headers.index("Статус_согласования"), REFERENCE_COLUMNS["E"][1:]),
            build_dropdown_request(exception_sheet_id, 1, 2000, exception_headers.index("Источник"), REFERENCE_COLUMNS["F"][1:]),
            build_dropdown_request(management_sheet_id, 1, 2000, management_headers.index("Тип_руководителя"), REFERENCE_COLUMNS["G"][1:]),
            build_dropdown_request(management_sheet_id, 1, 2000, management_headers.index("Основной"), REFERENCE_COLUMNS["C"][1:]),
            build_dropdown_request(substitution_sheet_id, 1, 2000, substitution_headers.index("Причина"), REFERENCE_COLUMNS["H"][1:]),
            build_dropdown_request(substitution_sheet_id, 1, 2000, substitution_headers.index("Распространяется_на_согласование"), REFERENCE_COLUMNS["C"][1:]),
            build_dropdown_request(substitution_sheet_id, 1, 2000, substitution_headers.index("Распространяется_на_отчеты"), REFERENCE_COLUMNS["C"][1:]),
            build_dropdown_request(substitution_sheet_id, 1, 2000, substitution_headers.index("Активно"), REFERENCE_COLUMNS["C"][1:]),
        ]
    )

    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests},
    ).execute()


def main():
    sheets_service, drive_service = create_services()
    if EXISTING_SPREADSHEET_ID:
        spreadsheet = get_existing_spreadsheet(sheets_service, EXISTING_SPREADSHEET_ID)
        spreadsheet_id = spreadsheet["spreadsheetId"]
        spreadsheet_url = spreadsheet["spreadsheetUrl"]
        sheet_map = get_sheet_map(sheets_service, spreadsheet_id)
        ensure_missing_sheets(sheets_service, spreadsheet_id, sheet_map)
        sheet_map = get_sheet_map(sheets_service, spreadsheet_id)
        write_initial_values(sheets_service, spreadsheet_id)
        staff_result = write_staff_data(sheets_service, spreadsheet_id)
        format_sheets(sheets_service, spreadsheet_id, sheet_map)

        print("Таблица обновлена:")
        print(spreadsheet_url)
        if staff_result["catalog_rows"] or staff_result["department_rows"]:
            print(
                f"Загружено сотрудников: {staff_result['catalog_rows']}, "
                f"подразделений: {staff_result['department_rows']}"
            )
        return
    else:
        spreadsheet = create_spreadsheet(drive_service, sheets_service)
    spreadsheet_id = spreadsheet["spreadsheetId"]
    spreadsheet_url = spreadsheet["spreadsheetUrl"]
    default_sheet_id = spreadsheet["sheets"][0]["properties"]["sheetId"]

    setup_sheets(sheets_service, spreadsheet_id, default_sheet_id)
    sheet_map = get_sheet_map(sheets_service, spreadsheet_id)
    write_initial_values(sheets_service, spreadsheet_id)
    staff_result = write_staff_data(sheets_service, spreadsheet_id)
    format_sheets(sheets_service, spreadsheet_id, sheet_map)

    print("Таблица создана:")
    print(spreadsheet_url)
    if staff_result["catalog_rows"] or staff_result["department_rows"]:
        print(
            f"Загружено сотрудников: {staff_result['catalog_rows']}, "
            f"подразделений: {staff_result['department_rows']}"
        )


if __name__ == "__main__":
    main()
