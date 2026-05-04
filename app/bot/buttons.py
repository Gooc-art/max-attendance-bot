from __future__ import annotations

from typing import Dict, List

from app.bot.actions import BotAction
from app.domain.enums import AttendanceReasonCode, Role, SubstitutionReason, SubstitutionScope
from app.schemas.max import MaxOutboundButton


def btn(title: str, action: str) -> MaxOutboundButton:
    return MaxOutboundButton(title=title, action=action)


def main_menu_buttons(role: str) -> List[MaxOutboundButton]:
    if role == Role.MANAGER.value:
        return [
            btn("Мои сотрудники", BotAction.MENU_EMPLOYEES),
            btn("Согласования", BotAction.MENU_APPROVALS),
            btn("Опоздания отдела", BotAction.MENU_DEPARTMENT_LATES),
            btn("Неявки отдела", BotAction.MENU_DEPARTMENT_ABSENCES),
            btn("Отчеты", BotAction.MENU_REPORTS),
            btn("Замещения", BotAction.MENU_SUBSTITUTIONS),
        ]
    if role == Role.SECURITY.value:
        return [
            btn("Загрузить выгрузку СКУД", BotAction.MENU_SECURITY_IMPORT),
            btn("История импортов", BotAction.MENU_IMPORT_HISTORY),
            btn("Ошибки сопоставления", BotAction.MENU_MATCH_ERRORS),
            btn("Необработанные записи", BotAction.MENU_UNPROCESSED),
        ]
    if role == Role.HR.value:
        return [
            btn("Сотрудники", BotAction.MENU_STAFF),
            btn("Подразделения", BotAction.MENU_DEPARTMENTS),
            btn("Графики", BotAction.MENU_SCHEDULES),
            btn("Исключения", BotAction.MENU_EXCEPTIONS),
            btn("Замещения", BotAction.MENU_SUBSTITUTIONS),
            btn("Согласования", BotAction.MENU_APPROVALS),
            btn("Отчеты", BotAction.MENU_REPORTS),
            btn("Системные настройки", BotAction.MENU_SETTINGS),
        ]
    if role == Role.ADMIN.value:
        return [
            btn("Мои уведомления", BotAction.MENU_MY_NOTIFICATIONS),
            btn("Мои опоздания", BotAction.MENU_MY_LATES),
            btn("Указать причину", BotAction.MENU_SUBMIT_REASON),
            btn("Мои статусы", BotAction.MENU_MY_STATUSES),
            btn("Мой руководитель", BotAction.MENU_MY_MANAGER),
            btn("Мои сотрудники", BotAction.MENU_EMPLOYEES),
            btn("Согласования", BotAction.MENU_APPROVALS),
            btn("Опоздания отдела", BotAction.MENU_DEPARTMENT_LATES),
            btn("Неявки отдела", BotAction.MENU_DEPARTMENT_ABSENCES),
            btn("Отчеты", BotAction.MENU_REPORTS),
            btn("Сводка", BotAction.MENU_SUMMARY),
            btn("Отчеты по подразделениям", BotAction.MENU_DIVISION_REPORTS),
            btn("Просроченные согласования", BotAction.MENU_OVERDUE_APPROVALS),
            btn("Замещения", BotAction.MENU_SUBSTITUTIONS),
            btn("Загрузить выгрузку СКУД", BotAction.MENU_SECURITY_IMPORT),
            btn("История импортов", BotAction.MENU_IMPORT_HISTORY),
            btn("Ошибки сопоставления", BotAction.MENU_MATCH_ERRORS),
            btn("Необработанные записи", BotAction.MENU_UNPROCESSED),
            btn("Сотрудники", BotAction.MENU_STAFF),
            btn("Подразделения", BotAction.MENU_DEPARTMENTS),
            btn("Графики", BotAction.MENU_SCHEDULES),
            btn("Исключения", BotAction.MENU_EXCEPTIONS),
            btn("Системные настройки", BotAction.MENU_SETTINGS),
            btn("Права доступа", BotAction.MENU_ACCESS_RIGHTS),
        ]
    if role == Role.TOP_MANAGER.value:
        return [
            btn("Сводка", BotAction.MENU_SUMMARY),
            btn("Отчеты по подразделениям", BotAction.MENU_DIVISION_REPORTS),
            btn("Просроченные согласования", BotAction.MENU_OVERDUE_APPROVALS),
            btn("Замещения", BotAction.MENU_SUBSTITUTIONS),
        ]
    return [
        btn("Мои уведомления", BotAction.MENU_MY_NOTIFICATIONS),
        btn("Мои опоздания", BotAction.MENU_MY_LATES),
        btn("Указать причину", BotAction.MENU_SUBMIT_REASON),
        btn("Мои статусы", BotAction.MENU_MY_STATUSES),
        btn("Мой руководитель", BotAction.MENU_MY_MANAGER),
    ]


def substitutions_menu_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Назначить замещение", BotAction.SUBSTITUTION_CREATE),
        btn("Мои замещения", BotAction.SUBSTITUTION_LIST),
        btn("Отменить замещение", BotAction.SUBSTITUTION_CANCEL),
        btn("Продлить замещение", BotAction.SUBSTITUTION_EXTEND),
        btn("Главное меню", BotAction.MAIN_MENU),
    ]


def approvals_menu_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Новые", BotAction.APPROVALS_NEW),
        btn("В работе", BotAction.APPROVALS_IN_PROGRESS),
        btn("Просроченные", BotAction.APPROVALS_OVERDUE),
        btn("История", BotAction.APPROVALS_HISTORY),
        btn("Главное меню", BotAction.MAIN_MENU),
    ]


def approval_card_buttons(approval_id: int) -> List[MaxOutboundButton]:
    return [
        btn("Согласовать", f"{BotAction.APPROVAL_APPROVE_PREFIX}{approval_id}"),
        btn("Отклонить", f"{BotAction.APPROVAL_REJECT_PREFIX}{approval_id}"),
        btn("К списку согласований", BotAction.MENU_APPROVALS),
        btn("Главное меню", BotAction.MAIN_MENU),
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
        buttons.append(btn("Указать причину", f"{BotAction.EMPLOYEE_CASE_OPEN_PREFIX}{case_id}"))
    buttons.append(btn("Главное меню", BotAction.MAIN_MENU))
    return buttons


def attendance_reason_buttons(case_id: int) -> List[MaxOutboundButton]:
    buttons = [
        btn(label, f"{BotAction.EMPLOYEE_REASON_PREFIX}{case_id}:{code}")
        for code, label in ATTENDANCE_REASON_LABELS.items()
    ]
    buttons.append(btn("Главное меню", BotAction.MAIN_MENU))
    return buttons


def reports_menu_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Недельный отчет", BotAction.REPORT_WEEK),
        btn("Месячный отчет", BotAction.REPORT_MONTH),
        btn("Квартальный отчет", BotAction.REPORT_QUARTER),
        btn("Главное меню", BotAction.MAIN_MENU),
    ]


def reason_buttons() -> List[MaxOutboundButton]:
    return [
        btn(SubstitutionReason.VACATION.value, SubstitutionReason.VACATION.value),
        btn(SubstitutionReason.SICK_LEAVE.value, SubstitutionReason.SICK_LEAVE.value),
        btn(SubstitutionReason.BUSINESS_TRIP.value, SubstitutionReason.BUSINESS_TRIP.value),
        btn(SubstitutionReason.OTHER.value, SubstitutionReason.OTHER.value),
        btn("Отмена", BotAction.CANCEL),
    ]


def scope_buttons() -> List[MaxOutboundButton]:
    return [
        btn(SubstitutionScope.APPROVALS.value, SubstitutionScope.APPROVALS.value),
        btn(SubstitutionScope.REPORTS.value, SubstitutionScope.REPORTS.value),
        btn(SubstitutionScope.BOTH.value, SubstitutionScope.BOTH.value),
        btn("Отмена", BotAction.CANCEL),
    ]


def confirm_buttons() -> List[MaxOutboundButton]:
    return [
        btn("Подтвердить", BotAction.CONFIRM),
        btn("Отмена", BotAction.CANCEL),
    ]
