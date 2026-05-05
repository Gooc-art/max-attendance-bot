from __future__ import annotations

from typing import Dict, List

from app.bot.actions import BotAction
from app.domain.enums import AttendanceReasonCode, Role, SubstitutionReason, SubstitutionScope
from app.schemas.max import MaxOutboundButton


def btn(title: str, action: str, emoji: str | None = None, row: int = 0) -> MaxOutboundButton:
    return MaxOutboundButton(title=title, action=action, emoji=emoji, row=row)


def main_menu_buttons(role: str) -> List[MaxOutboundButton]:
    if role == Role.MANAGER.value:
        return [
            btn("Старт", BotAction.START, "🏁", 0),
            btn("Кто я", BotAction.WHOAMI, "👤", 0),
            btn("Мои сотрудники", BotAction.MENU_EMPLOYEES, "👥", 1),
            btn("Согласования", BotAction.MENU_APPROVALS, "✅", 1),
            btn("Нарушения отдела", BotAction.MENU_DEPARTMENT_LATES, "⏱️", 2),
            btn("Отчеты", BotAction.MENU_REPORTS, "📊", 2),
            btn("Замещения", BotAction.MENU_SUBSTITUTIONS, "🔄", 3),
        ]
    if role == Role.SECURITY.value:
        return [
            btn("Старт", BotAction.START, "🏁", 0),
            btn("Кто я", BotAction.WHOAMI, "👤", 0),
            btn("Загрузить выгрузку СКУД", BotAction.MENU_SECURITY_IMPORT, "📥", 1),
            btn("История импортов", BotAction.MENU_IMPORT_HISTORY, "🕘", 1),
            btn("Ошибки сопоставления", BotAction.MENU_MATCH_ERRORS, "⚠️", 2),
            btn("Необработанные записи", BotAction.MENU_UNPROCESSED, "🗂️", 2),
        ]
    if role == Role.HR.value:
        return [
            btn("Старт", BotAction.START, "🏁", 0),
            btn("Кто я", BotAction.WHOAMI, "👤", 0),
            btn("Сотрудники", BotAction.MENU_STAFF, "👥", 1),
            btn("Подразделения", BotAction.MENU_DEPARTMENTS, "🏢", 1),
            btn("Графики", BotAction.MENU_SCHEDULES, "🗓️", 2),
            btn("Исключения", BotAction.MENU_EXCEPTIONS, "🚪", 2),
            btn("Замещения", BotAction.MENU_SUBSTITUTIONS, "🔄", 3),
            btn("Согласования", BotAction.MENU_APPROVALS, "✅", 3),
            btn("Отчеты", BotAction.MENU_REPORTS, "📊", 4),
            btn("Системные настройки", BotAction.MENU_SETTINGS, "⚙️", 4),
        ]
    if role == Role.ADMIN.value:
        return [
            btn("Старт", BotAction.START, "🏁", 0),
            btn("Кто я", BotAction.WHOAMI, "👤", 0),
            btn("Моя строка", BotAction.MENU_MY_ROW, "🪪", 1),
            btn("Проверить привязку", BotAction.MENU_BINDING_CHECK, "🔗", 1),
            btn("Админ-панель", BotAction.MENU_ADMIN_PANEL, "🛠️", 2),
            btn("Права доступа", BotAction.MENU_ACCESS_RIGHTS, "🔐", 2),
            btn("Сводка", BotAction.MENU_SUMMARY, "📈", 3),
            btn("Отчеты", BotAction.MENU_REPORTS, "📊", 3),
            btn("Согласования", BotAction.MENU_APPROVALS, "✅", 4),
            btn("Замещения", BotAction.MENU_SUBSTITUTIONS, "🔄", 4),
            btn("Мои уведомления", BotAction.MENU_MY_NOTIFICATIONS, "🔔", 5),
            btn("Мои опоздания", BotAction.MENU_MY_LATES, "⏰", 5),
            btn("Указать причину", BotAction.MENU_SUBMIT_REASON, "✍️", 6),
            btn("Мои статусы", BotAction.MENU_MY_STATUSES, "📎", 6),
            btn("Мой руководитель", BotAction.MENU_MY_MANAGER, "👔", 7),
            btn("Мои сотрудники", BotAction.MENU_EMPLOYEES, "👥", 7),
            btn("Опоздания отдела", BotAction.MENU_DEPARTMENT_LATES, "⏱️", 8),
            btn("Неявки отдела", BotAction.MENU_DEPARTMENT_ABSENCES, "🚫", 8),
            btn("Отчеты по подразделениям", BotAction.MENU_DIVISION_REPORTS, "🏢", 9),
            btn("Просроченные согласования", BotAction.MENU_OVERDUE_APPROVALS, "⛔", 9),
            btn("Загрузить выгрузку СКУД", BotAction.MENU_SECURITY_IMPORT, "📥", 10),
            btn("История импортов", BotAction.MENU_IMPORT_HISTORY, "🕘", 10),
            btn("Ошибки сопоставления", BotAction.MENU_MATCH_ERRORS, "⚠️", 11),
            btn("Необработанные записи", BotAction.MENU_UNPROCESSED, "🗂️", 11),
            btn("Сотрудники", BotAction.MENU_STAFF, "👥", 12),
            btn("Подразделения", BotAction.MENU_DEPARTMENTS, "🏢", 12),
            btn("Графики", BotAction.MENU_SCHEDULES, "🗓️", 13),
            btn("Исключения", BotAction.MENU_EXCEPTIONS, "🚪", 13),
            btn("Системные настройки", BotAction.MENU_SETTINGS, "⚙️", 14),
        ]
    if role == Role.TOP_MANAGER.value:
        return [
            btn("Старт", BotAction.START, "🏁", 0),
            btn("Кто я", BotAction.WHOAMI, "👤", 0),
            btn("Сводка", BotAction.MENU_SUMMARY, "📈", 1),
            btn("Отчеты по подразделениям", BotAction.MENU_DIVISION_REPORTS, "🏢", 1),
            btn("Просроченные согласования", BotAction.MENU_OVERDUE_APPROVALS, "⛔", 2),
            btn("Замещения", BotAction.MENU_SUBSTITUTIONS, "🔄", 2),
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
