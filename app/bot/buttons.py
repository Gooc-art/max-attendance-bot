from __future__ import annotations

from typing import Dict, List

from app.bot.actions import BotAction
from app.domain.enums import AttendanceReasonCode, Role, SubstitutionReason, SubstitutionScope
from app.schemas.max import MaxOutboundButton


def btn(title: str, action: str, emoji: str | None = None, row: int = 0) -> MaxOutboundButton:
    return MaxOutboundButton(title=title, action=action, emoji=emoji, row=row)


def main_menu_buttons(role: str) -> List[MaxOutboundButton]:
    if role == Role.EMPLOYEE.value:
        return [
            btn("Старт", BotAction.START, "🏁", 0),
            btn("Кто я", BotAction.WHOAMI, "👤", 0),
            btn("Личное", BotAction.EMPLOYEE_PERSONAL, "👤", 1),
            btn("Причины", BotAction.EMPLOYEE_REASONS, "✍️", 1),
            btn("Руководство", BotAction.EMPLOYEE_MANAGER, "👔", 2),
        ]
    if role == Role.MANAGER.value:
        return [
            btn("Старт", BotAction.START, "🏁", 0),
            btn("Кто я", BotAction.WHOAMI, "👤", 0),
            btn("Управление", BotAction.MANAGER_MANAGEMENT, "👥", 1),
            btn("Отчетный блок", BotAction.MANAGER_REPORTS, "📊", 1),
            btn("Замещения", BotAction.MENU_SUBSTITUTIONS, "🔄", 2),
            btn("Процессы", BotAction.MANAGER_WORKFLOW, "⏱️", 3),
        ]
    if role == Role.SECURITY.value:
        return [
            btn("Старт", BotAction.START, "🏁", 0),
            btn("Кто я", BotAction.WHOAMI, "👤", 0),
            btn("СКУД", BotAction.SECURITY_SKUD, "📥", 1),
            btn("Журнал", BotAction.MENU_IMPORT_HISTORY, "🕘", 1),
            btn("Очередь", BotAction.SECURITY_AUDIT, "🗂️", 2),
        ]
    if role == Role.HR.value:
        return [
            btn("Старт", BotAction.START, "🏁", 0),
            btn("Кто я", BotAction.WHOAMI, "👤", 0),
            btn("Справочники", BotAction.HR_REFERENCE, "👥", 1),
            btn("Процессы", BotAction.HR_WORKFLOW, "✅", 1),
            btn("Отчетный блок", BotAction.HR_REPORTS, "📊", 2),
            btn("Параметры", BotAction.HR_SETTINGS, "⚙️", 2),
        ]
    if role == Role.ADMIN.value:
        return [
            btn("Старт", BotAction.START, "🏁", 0),
            btn("Кто я", BotAction.WHOAMI, "👤", 0),
            btn("Админ-панель", BotAction.MENU_ADMIN_PANEL, "🛠️", 1),
            btn("Права доступа", BotAction.MENU_ACCESS_RIGHTS, "🔐", 1),
            btn("Личное", BotAction.ADMIN_PERSONAL, "👤", 2),
            btn("Структура", BotAction.ADMIN_STRUCTURE, "🏢", 2),
            btn("СКУД", BotAction.ADMIN_SKUD, "📥", 3),
            btn("Процессы", BotAction.ADMIN_WORKFLOW, "✅", 3),
            btn("Отчетный блок", BotAction.ADMIN_REPORTS, "📊", 4),
            btn("Параметры", BotAction.ADMIN_SETTINGS, "⚙️", 4),
        ]
    if role == Role.TOP_MANAGER.value:
        return [
            btn("Старт", BotAction.START, "🏁", 0),
            btn("Кто я", BotAction.WHOAMI, "👤", 0),
            btn("Аналитика", BotAction.TOP_SUMMARY, "📈", 1),
            btn("Отчетный блок", BotAction.TOP_REPORTS, "🏢", 1),
            btn("Процессы", BotAction.TOP_WORKFLOW, "⛔", 2),
        ]
    return [
        btn("Старт", BotAction.START, "🏁", 0),
        btn("Кто я", BotAction.WHOAMI, "👤", 0),
        btn("Мои уведомления", BotAction.MENU_MY_NOTIFICATIONS, "🔔", 1),
        btn("Мои опоздания", BotAction.MENU_MY_LATES, "⏰", 1),
        btn("Указать причину", BotAction.MENU_SUBMIT_REASON, "✍️", 2),
        btn("Мои статусы", BotAction.MENU_MY_STATUSES, "📎", 2),
        btn("Мой руководитель", BotAction.MENU_MY_MANAGER, "👔", 3),
    ]


def substitutions_menu_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Назначить замещение", BotAction.SUBSTITUTION_CREATE, "➕", 0),
        btn("Мои замещения", BotAction.SUBSTITUTION_LIST, "📋", 0),
        btn("Отменить замещение", BotAction.SUBSTITUTION_CANCEL, "🗑️", 1),
        btn("Продлить замещение", BotAction.SUBSTITUTION_EXTEND, "🔁", 1),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 2),
    ]


def approvals_menu_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Новые", BotAction.APPROVALS_NEW, "🆕", 0),
        btn("В работе", BotAction.APPROVALS_IN_PROGRESS, "🛠️", 0),
        btn("Просроченные", BotAction.APPROVALS_OVERDUE, "⛔", 1),
        btn("История", BotAction.APPROVALS_HISTORY, "🕘", 1),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 2),
    ]


def approval_card_buttons(approval_id: int) -> List[MaxOutboundButton]:
    return [
        btn("Согласовать", f"{BotAction.APPROVAL_APPROVE_PREFIX}{approval_id}", "✅", 0),
        btn("Отклонить", f"{BotAction.APPROVAL_REJECT_PREFIX}{approval_id}", "❌", 0),
        btn("К списку согласований", BotAction.MENU_APPROVALS, "📋", 1),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 1),
    ]


ATTENDANCE_REASON_LABELS: Dict[str, str] = {
    AttendanceReasonCode.SICK_LEAVE.value: "Больничный",
    AttendanceReasonCode.BUSINESS_TRIP.value: "Командировка",
    AttendanceReasonCode.REMOTE_DAY.value: "Удаленная работа",
    AttendanceReasonCode.APPROVED_LATE.value: "Согласованное опоздание",
    AttendanceReasonCode.PERSONAL_REASON.value: "Личная причина",
    AttendanceReasonCode.OTHER.value: "Другое",
}


def employee_case_buttons(case_id: int, require_reason: bool) -> List[MaxOutboundButton]:
    buttons: List[MaxOutboundButton] = []
    if require_reason:
        buttons.append(btn("Указать причину", f"{BotAction.EMPLOYEE_CASE_OPEN_PREFIX}{case_id}", "✍️", 0))
    buttons.append(btn("Главное меню", BotAction.MAIN_MENU, "🏠", 1))
    return buttons


def attendance_reason_buttons(case_id: int) -> List[MaxOutboundButton]:
    buttons = []
    icons = {
        AttendanceReasonCode.SICK_LEAVE.value: "🤒",
        AttendanceReasonCode.BUSINESS_TRIP.value: "🧳",
        AttendanceReasonCode.REMOTE_DAY.value: "🏠",
        AttendanceReasonCode.APPROVED_LATE.value: "✅",
        AttendanceReasonCode.PERSONAL_REASON.value: "📝",
        AttendanceReasonCode.OTHER.value: "⋯",
    }
    for index, (code, label) in enumerate(ATTENDANCE_REASON_LABELS.items()):
        buttons.append(btn(label, f"{BotAction.EMPLOYEE_REASON_PREFIX}{case_id}:{code}", icons.get(code), index // 2))
    buttons.append(btn("Главное меню", BotAction.MAIN_MENU, "🏠", 3))
    return buttons


def reports_menu_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Недельный отчет", BotAction.REPORT_WEEK, "📅", 0),
        btn("Месячный отчет", BotAction.REPORT_MONTH, "🗓️", 0),
        btn("Квартальный отчет", BotAction.REPORT_QUARTER, "📊", 1),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 2),
    ]


def employee_personal_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Мои уведомления", BotAction.MENU_MY_NOTIFICATIONS, "🔔", 0),
        btn("Мои опоздания", BotAction.MENU_MY_LATES, "⏰", 0),
        btn("Мои статусы", BotAction.MENU_MY_STATUSES, "📎", 1),
        btn("Мой руководитель", BotAction.MENU_MY_MANAGER, "👔", 1),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 2),
    ]


def employee_reason_section_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Указать причину", BotAction.MENU_SUBMIT_REASON, "✍️", 0),
        btn("Мои опоздания", BotAction.MENU_MY_LATES, "⏰", 0),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 1),
    ]


def employee_manager_section_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Мой руководитель", BotAction.MENU_MY_MANAGER, "👔", 0),
        btn("Мои уведомления", BotAction.MENU_MY_NOTIFICATIONS, "🔔", 0),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 1),
    ]


def manager_management_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Мои сотрудники", BotAction.MENU_EMPLOYEES, "👥", 0),
        btn("Опоздания отдела", BotAction.MENU_DEPARTMENT_LATES, "⏱️", 0),
        btn("Неявки отдела", BotAction.MENU_DEPARTMENT_ABSENCES, "🚫", 1),
        btn("Сводка", BotAction.MENU_SUMMARY, "📈", 1),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 2),
    ]


def manager_reports_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Отчеты", BotAction.MENU_REPORTS, "📊", 0),
        btn("Отчеты по подразделениям", BotAction.MENU_DIVISION_REPORTS, "🏢", 0),
        btn("Просроченные согласования", BotAction.MENU_OVERDUE_APPROVALS, "⛔", 1),
        btn("Сводка", BotAction.MENU_SUMMARY, "📈", 1),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 2),
    ]


def manager_workflow_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Согласования", BotAction.MENU_APPROVALS, "✅", 0),
        btn("Замещения", BotAction.MENU_SUBSTITUTIONS, "🔄", 0),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 1),
    ]


def security_skud_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Загрузить выгрузку СКУД", BotAction.MENU_SECURITY_IMPORT, "📥", 0),
        btn("История импортов", BotAction.MENU_IMPORT_HISTORY, "🕘", 0),
        btn("Ошибки сопоставления", BotAction.MENU_MATCH_ERRORS, "⚠️", 1),
        btn("Необработанные записи", BotAction.MENU_UNPROCESSED, "🗂️", 1),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 2),
    ]


def security_audit_buttons() -> List[MaxOutboundButton]:
    return [
        btn("История импортов", BotAction.MENU_IMPORT_HISTORY, "🕘", 0),
        btn("Ошибки сопоставления", BotAction.MENU_MATCH_ERRORS, "⚠️", 0),
        btn("Необработанные записи", BotAction.MENU_UNPROCESSED, "🗂️", 1),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 1),
    ]


def hr_reference_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Сотрудники", BotAction.MENU_STAFF, "👥", 0),
        btn("Подразделения", BotAction.MENU_DEPARTMENTS, "🏢", 0),
        btn("Графики", BotAction.MENU_SCHEDULES, "🗓️", 1),
        btn("Исключения", BotAction.MENU_EXCEPTIONS, "🚪", 1),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 2),
    ]


def hr_workflow_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Замещения", BotAction.MENU_SUBSTITUTIONS, "🔄", 0),
        btn("Согласования", BotAction.MENU_APPROVALS, "✅", 0),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 1),
    ]


def hr_reports_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Отчеты", BotAction.MENU_REPORTS, "📊", 0),
        btn("Отчеты по подразделениям", BotAction.MENU_DIVISION_REPORTS, "🏢", 0),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 1),
    ]


def hr_settings_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Системные настройки", BotAction.MENU_SETTINGS, "⚙️", 0),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 1),
    ]


def top_summary_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Сводка", BotAction.MENU_SUMMARY, "📈", 0),
        btn("Просроченные согласования", BotAction.MENU_OVERDUE_APPROVALS, "⛔", 0),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 1),
    ]


def top_reports_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Отчеты по подразделениям", BotAction.MENU_DIVISION_REPORTS, "🏢", 0),
        btn("Отчеты", BotAction.MENU_REPORTS, "📊", 0),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 1),
    ]


def top_workflow_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Согласования", BotAction.MENU_APPROVALS, "✅", 0),
        btn("Замещения", BotAction.MENU_SUBSTITUTIONS, "🔄", 0),
        btn("Просроченные согласования", BotAction.MENU_OVERDUE_APPROVALS, "⛔", 1),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 1),
    ]


def reason_buttons() -> List[MaxOutboundButton]:
    return [
        btn(SubstitutionReason.VACATION.value, SubstitutionReason.VACATION.value, "🏖️", 0),
        btn(SubstitutionReason.SICK_LEAVE.value, SubstitutionReason.SICK_LEAVE.value, "🤒", 0),
        btn(SubstitutionReason.BUSINESS_TRIP.value, SubstitutionReason.BUSINESS_TRIP.value, "🧳", 1),
        btn(SubstitutionReason.OTHER.value, SubstitutionReason.OTHER.value, "⋯", 1),
        btn("Отмена", BotAction.CANCEL, "✖️", 2),
    ]


def scope_buttons() -> List[MaxOutboundButton]:
    return [
        btn(SubstitutionScope.APPROVALS.value, SubstitutionScope.APPROVALS.value, "✅", 0),
        btn(SubstitutionScope.REPORTS.value, SubstitutionScope.REPORTS.value, "📊", 0),
        btn(SubstitutionScope.BOTH.value, SubstitutionScope.BOTH.value, "🔄", 1),
        btn("Отмена", BotAction.CANCEL, "✖️", 1),
    ]


def confirm_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Подтвердить", BotAction.CONFIRM, "✅", 0),
        btn("Отмена", BotAction.CANCEL, "✖️", 0),
    ]


def admin_personal_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Кто я", BotAction.WHOAMI, "👤", 0),
        btn("Моя строка", BotAction.MENU_MY_ROW, "🪪", 0),
        btn("Проверить привязку", BotAction.MENU_BINDING_CHECK, "🔗", 1),
        btn("Права доступа", BotAction.MENU_ACCESS_RIGHTS, "🔐", 1),
        btn("Админ-панель", BotAction.MENU_ADMIN_PANEL, "🛠️", 2),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 2),
    ]


def admin_structure_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Сотрудники", BotAction.MENU_STAFF, "👥", 0),
        btn("Подразделения", BotAction.MENU_DEPARTMENTS, "🏢", 0),
        btn("Графики", BotAction.MENU_SCHEDULES, "🗓️", 1),
        btn("Исключения", BotAction.MENU_EXCEPTIONS, "🚪", 1),
        btn("Админ-панель", BotAction.MENU_ADMIN_PANEL, "🛠️", 2),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 2),
    ]


def admin_skud_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Загрузить выгрузку СКУД", BotAction.MENU_SECURITY_IMPORT, "📥", 0),
        btn("История импортов", BotAction.MENU_IMPORT_HISTORY, "🕘", 0),
        btn("Ошибки сопоставления", BotAction.MENU_MATCH_ERRORS, "⚠️", 1),
        btn("Необработанные записи", BotAction.MENU_UNPROCESSED, "🗂️", 1),
        btn("Админ-панель", BotAction.MENU_ADMIN_PANEL, "🛠️", 2),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 2),
    ]


def admin_workflow_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Согласования", BotAction.MENU_APPROVALS, "✅", 0),
        btn("Нарушения отдела", BotAction.MENU_DEPARTMENT_LATES, "⏱️", 0),
        btn("Неявки отдела", BotAction.MENU_DEPARTMENT_ABSENCES, "🚫", 1),
        btn("Замещения", BotAction.MENU_SUBSTITUTIONS, "🔄", 1),
        btn("Просроченные согласования", BotAction.MENU_OVERDUE_APPROVALS, "⛔", 2),
        btn("Админ-панель", BotAction.MENU_ADMIN_PANEL, "🛠️", 2),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 3),
    ]


def admin_reports_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Сводка", BotAction.MENU_SUMMARY, "📈", 0),
        btn("Отчеты", BotAction.MENU_REPORTS, "📊", 0),
        btn("Отчеты по подразделениям", BotAction.MENU_DIVISION_REPORTS, "🏢", 1),
        btn("Админ-панель", BotAction.MENU_ADMIN_PANEL, "🛠️", 1),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 2),
    ]


def admin_settings_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Системные настройки", BotAction.MENU_SETTINGS, "⚙️", 0),
        btn("Админ-панель", BotAction.MENU_ADMIN_PANEL, "🛠️", 1),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 1),
    ]
