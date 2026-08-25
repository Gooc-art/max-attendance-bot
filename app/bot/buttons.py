from __future__ import annotations

from typing import Dict, List

from app.bot.actions import BotAction
from app.domain.enums import AttendanceReasonCode, Role, SubstitutionReason, SubstitutionScope
from app.schemas.max import MaxOutboundButton


def btn(title: str, action: str, emoji: str | None = None, row: int = 0) -> MaxOutboundButton:
    return MaxOutboundButton(title=title, action=action, emoji=emoji, row=row)


def _button_text_width(button: MaxOutboundButton) -> int:
    title = (button.title or "").strip()
    emoji_prefix_width = 2 if button.emoji else 0
    padding_width = 2
    return len(title) + emoji_prefix_width + padding_width


def readable_rows(
    buttons: List[MaxOutboundButton],
    *,
    max_per_row: int = 2,
    long_title_threshold: int = 12,
    row_width_limit: int = 20,
) -> List[MaxOutboundButton]:
    laid_out: List[MaxOutboundButton] = []
    current_row = 0
    row_width = 0
    row_items = 0

    for original in buttons:
        title_width = _button_text_width(original)
        force_single = title_width > long_title_threshold
        next_width = row_width + title_width

        if force_single:
            if row_items:
                current_row += 1
            laid_out.append(
                MaxOutboundButton(
                    title=original.title,
                    action=original.action,
                    emoji=original.emoji,
                    row=current_row,
                    button_type=original.button_type,
                    url=original.url,
                )
            )
            current_row += 1
            row_width = 0
            row_items = 0
            continue

        if row_items >= max_per_row or (row_items and next_width > row_width_limit):
            current_row += 1
            row_width = 0
            row_items = 0

        laid_out.append(
            MaxOutboundButton(
                title=original.title,
                action=original.action,
                emoji=original.emoji,
                row=current_row,
                button_type=original.button_type,
                url=original.url,
            )
        )
        row_width += title_width
        row_items += 1

    return laid_out


def main_menu_buttons(role: str) -> List[MaxOutboundButton]:
    if role == Role.EMPLOYEE.value:
        return readable_rows([
            btn("Обо мне", BotAction.WHOAMI, "👤", 0),
            btn("Опаздываю", BotAction.MENU_RUNNING_LATE, "🚕", 0),
            btn("Отпроситься", BotAction.MENU_SHORT_LEAVE, "🚪", 1),
            btn("Забыл карточку СКУД", BotAction.MENU_FORGOT_CHIP, "🪪", 1),
            btn("Опоздания", BotAction.EMPLOYEE_REASONS, "⏰", 2),
            btn("Руководство", BotAction.EMPLOYEE_MANAGER, "👔", 2),
            btn("Погода", BotAction.MENU_WEATHER, "🌤️", 3),
        ])
    if role == Role.MANAGER.value:
        return readable_rows([
            btn("Обо мне", BotAction.WHOAMI, "👤", 0),
            btn("Опаздываю", BotAction.MENU_RUNNING_LATE, "🚕", 0),
            btn("Отпроситься", BotAction.MENU_SHORT_LEAVE, "🚪", 1),
            btn("Забыл карточку СКУД", BotAction.MENU_FORGOT_CHIP, "🪪", 1),
            btn("Команда", BotAction.MANAGER_MANAGEMENT, "👥", 1),
            btn("Согласования", BotAction.MENU_APPROVALS, "✅", 1),
            btn("Замещения", BotAction.MENU_SUBSTITUTIONS, "🔄", 3),
            btn("Погода", BotAction.MENU_WEATHER, "🌤️", 4),
        ])
    if role == Role.SECURITY.value:
        return readable_rows([
            btn("Обо мне", BotAction.WHOAMI, "👤", 0),
            btn("Опаздываю", BotAction.MENU_RUNNING_LATE, "🚕", 0),
            btn("Отпроситься", BotAction.MENU_SHORT_LEAVE, "🚪", 1),
            btn("Забыл карточку СКУД", BotAction.MENU_FORGOT_CHIP, "🪪", 1),
            btn("СКУД", BotAction.SECURITY_SKUD, "📥", 1),
            btn("Погода", BotAction.MENU_WEATHER, "🌤️", 2),
        ])
    if role == Role.HR.value:
        return readable_rows([
            btn("Обо мне", BotAction.WHOAMI, "👤", 0),
            btn("Опаздываю", BotAction.MENU_RUNNING_LATE, "🚕", 0),
            btn("Отпроситься", BotAction.MENU_SHORT_LEAVE, "🚪", 1),
            btn("Забыл карточку СКУД", BotAction.MENU_FORGOT_CHIP, "🪪", 1),
            btn("Справочники", BotAction.HR_REFERENCE, "👥", 1),
            btn("Процессы", BotAction.HR_WORKFLOW, "✅", 1),
            btn("Отчеты", BotAction.HR_REPORTS, "📊", 1),
            btn("Погода", BotAction.MENU_WEATHER, "🌤️", 2),
        ])
    if role == Role.ADMIN.value:
        return readable_rows([
            btn("Обо мне", BotAction.WHOAMI, "👤", 0),
            btn("Опаздываю", BotAction.MENU_RUNNING_LATE, "🚕", 0),
            btn("Отпроситься", BotAction.MENU_SHORT_LEAVE, "🚪", 1),
            btn("Забыл карточку СКУД", BotAction.MENU_FORGOT_CHIP, "🪪", 1),
            btn("Личное", BotAction.ADMIN_PERSONAL, "👤", 1),
            btn("Структура", BotAction.ADMIN_STRUCTURE, "🏢", 1),
            btn("СКУД", BotAction.ADMIN_SKUD, "📥", 1),
            btn("Процессы", BotAction.ADMIN_WORKFLOW, "✅", 2),
            btn("Отчеты", BotAction.ADMIN_REPORTS, "📊", 2),
            btn("Погода", BotAction.MENU_WEATHER, "🌤️", 3),
        ])
    if role == Role.TOP_MANAGER.value:
        return readable_rows([
            btn("Обо мне", BotAction.WHOAMI, "👤", 0),
            btn("Аналитика", BotAction.TOP_SUMMARY, "📈", 0),
            btn("Согласования", BotAction.MENU_APPROVALS, "✅", 1),
            btn("Отчеты", BotAction.TOP_REPORTS, "📊", 1),
            btn("СКУД", BotAction.SECURITY_SKUD, "📥", 2),
            btn("Замещения", BotAction.MENU_SUBSTITUTIONS, "🔄", 3),
            btn("Погода", BotAction.MENU_WEATHER, "🌤️", 4),
        ])
    return readable_rows([
        btn("Старт", BotAction.START, "🏁", 0),
        btn("Обо мне", BotAction.WHOAMI, "👤", 0),
        btn("Уведомления", BotAction.MENU_MY_NOTIFICATIONS, "🔔", 1),
        btn("Мои опоздания", BotAction.MENU_MY_LATES, "⏰", 1),
        btn("Объяснить", BotAction.MENU_SUBMIT_REASON, "✍️", 2),
        btn("Мои статусы", BotAction.MENU_MY_STATUSES, "📎", 2),
        btn("Руководитель", BotAction.MENU_MY_MANAGER, "👔", 3),
    ])


def substitutions_menu_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn("На период", BotAction.SUBSTITUTION_CREATE, "➕", 0),
        btn("Мои замещения", BotAction.SUBSTITUTION_LIST, "📋", 0),
        btn("Снять замещение", BotAction.SUBSTITUTION_CANCEL, "🗑️", 1),
        btn("Продлить", BotAction.SUBSTITUTION_EXTEND, "🔁", 1),
        btn("Назад", BotAction.MAIN_MENU, "↩️", 2),
    ])


def approvals_menu_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn("Ожидают", BotAction.APPROVALS_NEW, "🆕", 0),
        btn("Просроченные", BotAction.APPROVALS_OVERDUE, "⛔", 1),
        btn("История согласований", BotAction.APPROVALS_HISTORY, "🕘", 2),
        btn("Назад", BotAction.MAIN_MENU, "↩️", 3),
    ])


def approval_card_buttons(approval_id: int) -> List[MaxOutboundButton]:
    return readable_rows([
        btn("Согласовать", f"{BotAction.APPROVAL_APPROVE_PREFIX}{approval_id}", "✅", 0),
        btn("Отклонить", f"{BotAction.APPROVAL_REJECT_PREFIX}{approval_id}", "❌", 0),
        btn("К списку", BotAction.MENU_APPROVALS, "📋", 1),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 1),
    ])


def approval_notification_buttons(approval_id: int) -> List[MaxOutboundButton]:
    return readable_rows([
        btn("Открыть", f"{BotAction.APPROVAL_OPEN_PREFIX}{approval_id}", "📋", 0),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 0),
    ])


def substitution_notification_buttons(draft_id: int) -> List[MaxOutboundButton]:
    return readable_rows([
        btn("Открыть", f"{BotAction.SUBSTITUTION_OPEN_PREFIX}{draft_id}", "📋", 0),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 0),
    ])


def substitution_approval_card_buttons(draft_id: int) -> List[MaxOutboundButton]:
    return readable_rows([
        btn("Согласовать", f"{BotAction.SUBSTITUTION_APPROVE_PREFIX}{draft_id}", "✅", 0),
        btn("Отклонить", f"{BotAction.SUBSTITUTION_REJECT_PREFIX}{draft_id}", "❌", 0),
        btn("К списку", BotAction.MENU_SUBSTITUTIONS, "📋", 1),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 1),
    ])


ATTENDANCE_REASON_LABELS: Dict[str, str] = {
    AttendanceReasonCode.VACATION.value: "Отпуск",
    AttendanceReasonCode.SICK_LEAVE.value: "Больничный",
    AttendanceReasonCode.BUSINESS_TRIP.value: "Командировка",
    AttendanceReasonCode.REMOTE_DAY.value: "Удаленка",
    AttendanceReasonCode.APPROVED_LATE.value: "Согласовано",
    AttendanceReasonCode.PERSONAL_REASON.value: "Личная причина",
    AttendanceReasonCode.OTHER.value: "Другое",
}

LATE_NOTICE_REASON_LABELS: Dict[str, str] = {
    AttendanceReasonCode.OTHER.value: "Другое",
}


def employee_case_buttons(case_id: int, require_reason: bool, allow_return_early: bool = False) -> List[MaxOutboundButton]:
    buttons: List[MaxOutboundButton] = []
    if require_reason:
        buttons.append(btn("Объяснить", f"{BotAction.EMPLOYEE_CASE_OPEN_PREFIX}{case_id}", "✍️", 0))
    if allow_return_early:
        buttons.append(btn("Выйду раньше", f"{BotAction.EMPLOYEE_CASE_RETURN_EARLY_PREFIX}{case_id}", "📅", 0))
    buttons.append(btn("Назад", BotAction.MENU_MY_LATES, "↩️", 1))
    buttons.append(btn("Главное меню", BotAction.MAIN_MENU, "🏠", 1))
    return readable_rows(buttons)


def attendance_reason_buttons(case_id: int) -> List[MaxOutboundButton]:
    buttons = []
    icons = {
        AttendanceReasonCode.VACATION.value: "🏖️",
        AttendanceReasonCode.SICK_LEAVE.value: "🤒",
        AttendanceReasonCode.BUSINESS_TRIP.value: "🧳",
        AttendanceReasonCode.REMOTE_DAY.value: "🏠",
        AttendanceReasonCode.APPROVED_LATE.value: "✅",
        AttendanceReasonCode.PERSONAL_REASON.value: "📝",
        AttendanceReasonCode.OTHER.value: "⋯",
    }
    for code, label in ATTENDANCE_REASON_LABELS.items():
        buttons.append(btn(label, f"{BotAction.EMPLOYEE_REASON_PREFIX}{case_id}:{code}", icons.get(code), 0))
    buttons.append(btn("Назад", BotAction.BACK, "↩️", 3))
    buttons.append(btn("Главное меню", BotAction.MAIN_MENU, "🏠", 3))
    return readable_rows(buttons, max_per_row=1, long_title_threshold=1, row_width_limit=99)


def reports_menu_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn("За период", BotAction.REPORT_CUSTOM, "📅", 0),
        btn("По отделам", BotAction.MENU_DIVISION_REPORTS, "🏢", 0),
        btn("Недельный", BotAction.REPORT_WEEK, "🗓️", 1),
        btn("Месячный", BotAction.REPORT_MONTH, "📊", 1),
        btn("Квартал", BotAction.REPORT_QUARTER, "📈", 2),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 3),
    ])


def employee_personal_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn("Мои статусы", BotAction.MENU_MY_STATUSES, "📎", 0),
        btn("Назад", BotAction.MAIN_MENU, "↩️", 1),
    ])


def employee_reason_section_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn("Объяснить", BotAction.MENU_SUBMIT_REASON, "✍️", 0),
        btn("Опаздываю", BotAction.MENU_RUNNING_LATE, "🚕", 0),
        btn("Отпроситься", BotAction.MENU_SHORT_LEAVE, "🚪", 0),
        btn("Забыл карточку СКУД", BotAction.MENU_FORGOT_CHIP, "🪪", 0),
        btn("Мои опоздания", BotAction.MENU_MY_LATES, "⏰", 0),
        btn("Назад", BotAction.MAIN_MENU, "↩️", 2),
    ])


def employee_manager_section_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn("Руководитель", BotAction.MENU_MY_MANAGER, "👔", 0),
        btn("Уведомления", BotAction.MENU_MY_NOTIFICATIONS, "🔔", 0),
        btn("Мой кабинет", BotAction.MENU_MY_OFFICE, "🚪", 1),
        btn("Назад", BotAction.MAIN_MENU, "↩️", 2),
    ])


def manager_management_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn("Мои сотрудники", BotAction.MENU_EMPLOYEES, "👥", 0),
        btn("Опоздания", BotAction.MENU_DEPARTMENT_LATES, "⏱️", 0),
        btn("Неявки отдела", BotAction.MENU_DEPARTMENT_ABSENCES, "🚫", 1),
        btn("Сводка", BotAction.MENU_SUMMARY, "📈", 1),
        btn("Устройства", BotAction.REPORT_DEVICES, "📱", 2),
        btn("Назад", BotAction.MAIN_MENU, "↩️", 3),
    ])


def manager_reports_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn("Загрузить отчет", BotAction.MENU_SECURITY_IMPORT, "📥", 0),
        btn("За период", BotAction.REPORT_CUSTOM, "📅", 0),
        btn("По отделам", BotAction.MENU_DIVISION_REPORTS, "🏢", 0),
        btn("Недельный", BotAction.REPORT_WEEK, "🗓️", 1),
        btn("Месячный", BotAction.REPORT_MONTH, "📊", 1),
        btn("Квартал", BotAction.REPORT_QUARTER, "📈", 2),
        btn("Устройства", BotAction.REPORT_DEVICES, "📱", 2),
        btn("Назад", BotAction.MAIN_MENU, "↩️", 3),
    ])


def manager_workflow_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn("Согласования", BotAction.MENU_APPROVALS, "✅", 0),
        btn("Замещения", BotAction.MENU_SUBSTITUTIONS, "🔄", 0),
        btn("Назад", BotAction.MAIN_MENU, "↩️", 1),
    ])


def security_skud_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn("Импорт СКУД", BotAction.MENU_SECURITY_IMPORT, "📥", 0),
        btn("История импортов", BotAction.MENU_IMPORT_HISTORY, "🕘", 0),
        btn("Назад", BotAction.MAIN_MENU, "↩️", 1),
    ])


def hr_reference_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn("Сотрудники", BotAction.MENU_STAFF, "👥", 0),
        btn("Подразделения", BotAction.MENU_DEPARTMENTS, "🏢", 0),
        btn("Назад", BotAction.MAIN_MENU, "↩️", 1),
    ])


def hr_workflow_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn("Замещения", BotAction.MENU_SUBSTITUTIONS, "🔄", 0),
        btn("Согласования", BotAction.MENU_APPROVALS, "✅", 0),
        btn("Назад", BotAction.MAIN_MENU, "↩️", 1),
    ])


def hr_reports_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn("Отчеты", BotAction.MENU_REPORTS, "📊", 0),
        btn("По отделам", BotAction.MENU_DIVISION_REPORTS, "🏢", 0),
        btn("Назад", BotAction.MAIN_MENU, "↩️", 1),
    ])


def top_summary_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn("Сводка", BotAction.MENU_SUMMARY, "📈", 0),
        btn("Статистика отделов", BotAction.MENU_DEPARTMENT_ABSENCES, "🏢", 1),
        btn("Просроченные", BotAction.MENU_OVERDUE_APPROVALS, "⛔", 1),
        btn("По отделам", BotAction.MENU_DIVISION_REPORTS, "🏢", 2),
        btn("Устройства", BotAction.REPORT_DEVICES, "📱", 2),
        btn("Входы", BotAction.MENU_BOT_ACTIVITY, "🚪", 3),
        btn("Назад", BotAction.MAIN_MENU, "↩️", 4),
    ])


def top_reports_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn("За период", BotAction.REPORT_CUSTOM, "📅", 0),
        btn("По отделам", BotAction.MENU_DIVISION_REPORTS, "🏢", 0),
        btn("Недельный", BotAction.REPORT_WEEK, "🗓️", 1),
        btn("Месячный", BotAction.REPORT_MONTH, "📊", 1),
        btn("Квартал", BotAction.REPORT_QUARTER, "📈", 2),
        btn("Устройства", BotAction.REPORT_DEVICES, "📱", 2),
        btn("Назад", BotAction.MAIN_MENU, "↩️", 3),
    ])


def top_workflow_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn("Согласования", BotAction.MENU_APPROVALS, "✅", 0),
        btn("Замещения", BotAction.MENU_SUBSTITUTIONS, "🔄", 0),
        btn("Назад", BotAction.MAIN_MENU, "↩️", 1),
    ])


def reason_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn(SubstitutionReason.VACATION.value, SubstitutionReason.VACATION.value, "🏖️", 0),
        btn(SubstitutionReason.SICK_LEAVE.value, SubstitutionReason.SICK_LEAVE.value, "🤒", 0),
        btn(SubstitutionReason.BUSINESS_TRIP.value, SubstitutionReason.BUSINESS_TRIP.value, "🧳", 1),
        btn(SubstitutionReason.OTHER.value, SubstitutionReason.OTHER.value, "⋯", 1),
        btn("Отмена", BotAction.CANCEL, "✖️", 2),
    ])


def scope_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn(SubstitutionScope.APPROVALS.value, SubstitutionScope.APPROVALS.value, "✅", 0),
        btn(SubstitutionScope.REPORTS.value, SubstitutionScope.REPORTS.value, "📊", 0),
        btn(SubstitutionScope.BOTH.value, SubstitutionScope.BOTH.value, "🔄", 1),
        btn("Отмена", BotAction.CANCEL, "✖️", 1),
    ])


def confirm_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn("Подтвердить", BotAction.CONFIRM, "✅", 0),
        btn("Отмена", BotAction.CANCEL, "✖️", 0),
    ])


def admin_personal_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn("Обо мне", BotAction.WHOAMI, "👤", 0),
        btn("Моя строка", BotAction.MENU_MY_ROW, "🪪", 0),
        btn("Привязка", BotAction.MENU_BINDING_CHECK, "🔗", 1),
        btn("Опаздываю", BotAction.MENU_RUNNING_LATE, "🚕", 1),
        btn("Забыл карточку СКУД", BotAction.MENU_FORGOT_CHIP, "🪪", 1),
        btn("Права доступа", BotAction.MENU_ACCESS_RIGHTS, "🔐", 2),
        btn("Админ-панель", BotAction.MENU_ADMIN_PANEL, "🛠️", 2),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 3),
    ])


def running_late_reason_buttons() -> List[MaxOutboundButton]:
    buttons = [
        btn("Указать причину", f"{BotAction.LATE_NOTICE_REASON_PREFIX}{AttendanceReasonCode.OTHER.value}", "✍️", 0)
    ]
    buttons.append(btn("Назад", BotAction.BACK, "↩️", 3))
    buttons.append(btn("Главное меню", BotAction.MAIN_MENU, "🏠", 3))
    return readable_rows(buttons, max_per_row=1, long_title_threshold=1, row_width_limit=99)


def running_late_date_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn("Сегодня", f"{BotAction.LATE_NOTICE_DATE_PREFIX}today", "📅", 0),
        btn("Завтра", f"{BotAction.LATE_NOTICE_DATE_PREFIX}tomorrow", "➡️", 0),
        btn("Назад", BotAction.BACK, "↩️", 1),
        btn("Главное меню", BotAction.MAIN_MENU, "🏠", 1),
    ], max_per_row=1, long_title_threshold=1, row_width_limit=99)


def admin_structure_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn("Сотрудники", BotAction.MENU_STAFF, "👥", 0),
        btn("Подразделения", BotAction.MENU_DEPARTMENTS, "🏢", 0),
        btn("Назад", BotAction.MAIN_MENU, "↩️", 1),
    ])


def admin_skud_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn("Импорт СКУД", BotAction.MENU_SECURITY_IMPORT, "📥", 0),
        btn("История импортов", BotAction.MENU_IMPORT_HISTORY, "🕘", 0),
        btn("Назад", BotAction.MAIN_MENU, "↩️", 1),
    ])


def admin_workflow_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn("Согласования", BotAction.MENU_APPROVALS, "✅", 0),
        btn("Нарушения", BotAction.MENU_DEPARTMENT_LATES, "⏱️", 0),
        btn("Неявки отдела", BotAction.MENU_DEPARTMENT_ABSENCES, "🚫", 1),
        btn("Замещения", BotAction.MENU_SUBSTITUTIONS, "🔄", 1),
        btn("Просроченные", BotAction.MENU_OVERDUE_APPROVALS, "⛔", 2),
        btn("Назад", BotAction.MAIN_MENU, "↩️", 3),
    ])


def admin_reports_buttons() -> List[MaxOutboundButton]:
    return readable_rows([
        btn("Сводка", BotAction.MENU_SUMMARY, "📈", 0),
        btn("Отчеты", BotAction.MENU_REPORTS, "📊", 0),
        btn("По отделам", BotAction.MENU_DIVISION_REPORTS, "🏢", 1),
        btn("Назад", BotAction.MAIN_MENU, "↩️", 2),
    ])
