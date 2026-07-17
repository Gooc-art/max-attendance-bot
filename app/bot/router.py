from __future__ import annotations

import logging
import threading
import re
from hashlib import sha256
from datetime import datetime, timedelta
from time import monotonic, perf_counter
from typing import List, Optional, Tuple

from app.bot.actions import BotAction
from app.bot.buttons import (
    admin_personal_buttons,
    admin_reports_buttons,
    admin_skud_buttons,
    admin_structure_buttons,
    admin_workflow_buttons,
    ATTENDANCE_REASON_LABELS,
    LATE_NOTICE_REASON_LABELS,
    approval_card_buttons,
    approval_notification_buttons,
    approvals_menu_buttons,
    attendance_reason_buttons,
    employee_case_buttons,
    employee_manager_section_buttons,
    employee_personal_buttons,
    employee_reason_section_buttons,
    hr_reference_buttons,
    hr_reports_buttons,
    hr_workflow_buttons,
    manager_management_buttons,
    manager_reports_buttons,
    manager_workflow_buttons,
    main_menu_buttons,
    reports_menu_buttons,
    running_late_date_buttons,
    running_late_reason_buttons,
    security_skud_buttons,
    substitution_approval_card_buttons,
    substitution_notification_buttons,
    top_reports_buttons,
    top_summary_buttons,
    top_workflow_buttons,
    substitutions_menu_buttons,
)
from app.bot.menus import get_menu_for_role
from app.config import get_settings
from app.db.models import utc_now
from app.domain.enums import ApprovalStatus, AttendanceCaseStatus, AttendanceCaseType, AttendanceReasonCode, DialogFlow, Role
from app.domain.dialog_state import UserDialogState
from app.domain.role_labels import display_role_name
from app.integrations.max.client import INVISIBLE_MESSAGE_TEXT, MaxApiClient
from app.integrations.google_sheets.directory import GoogleSheetsDirectoryService
from app.integrations.google_sheets.schedules import GoogleSheetsScheduleService
from app.repositories.approval_repository import ApprovalRepository
from app.repositories.attendance_case_repository import AttendanceCaseRepository
from app.repositories.employee_directory_repository import EmployeeDirectoryRepository
from app.repositories.user_bot_activity_repository import UserBotActivityRepository
from app.services.report_service import ReportService
from app.repositories.skud_import_repository import SkudImportRepository
from app.repositories.substitution_repository import SubstitutionRepository
from app.repositories.runtime_marker_repository import RuntimeMarkerRepository
from app.repositories.user_role_override_repository import UserRoleOverrideRepository
from app.schemas.max import MaxAttachment, MaxOutboundButton, MaxOutboundMessage, MaxUpdate, MaxWebhookResponse
from app.services.bot_message_cursor import bot_message_cursor_store
from app.services.dialog_state import dialog_state_store
from app.services.max_file_import import MaxFileImportService
from app.services.office_sealing import OfficeSealingService
from app.services.role_resolver import RoleResolver
from app.services.substitution_flow import SubstitutionFlowService


MANAGER_ROLES = {Role.MANAGER.value, Role.ADMIN.value, Role.TOP_MANAGER.value}
STRUCTURE_ROLES = {Role.HR.value, Role.ADMIN.value}
SKUD_ROLES = {Role.MANAGER.value, Role.SECURITY.value, Role.ADMIN.value, Role.TOP_MANAGER.value}
WORKFLOW_ROLES = {Role.MANAGER.value, Role.HR.value, Role.ADMIN.value, Role.TOP_MANAGER.value}
REPORT_ROLES = {Role.MANAGER.value, Role.HR.value, Role.ADMIN.value, Role.TOP_MANAGER.value}

ACTION_ALLOWED_ROLES = {
    BotAction.MANAGER_MANAGEMENT: MANAGER_ROLES,
    BotAction.MANAGER_REPORTS: {Role.MANAGER.value},
    BotAction.MANAGER_WORKFLOW: {Role.MANAGER.value},
    BotAction.MENU_EMPLOYEES: MANAGER_ROLES,
    BotAction.MENU_DEPARTMENT_LATES: MANAGER_ROLES,
    BotAction.MENU_DEPARTMENT_ABSENCES: MANAGER_ROLES,
    BotAction.MENU_SUMMARY: MANAGER_ROLES,
    BotAction.SECURITY_SKUD: {Role.SECURITY.value, Role.TOP_MANAGER.value},
    BotAction.SECURITY_AUDIT: set(),
    BotAction.MENU_SECURITY_IMPORT: SKUD_ROLES,
    BotAction.MENU_IMPORT_HISTORY: SKUD_ROLES,
    BotAction.MENU_MATCH_ERRORS: set(),
    BotAction.MENU_UNPROCESSED: set(),
    BotAction.HR_REFERENCE: {Role.HR.value},
    BotAction.HR_WORKFLOW: {Role.HR.value},
    BotAction.HR_REPORTS: {Role.HR.value},
    BotAction.HR_SETTINGS: set(),
    BotAction.MENU_STAFF: STRUCTURE_ROLES,
    BotAction.MENU_DEPARTMENTS: STRUCTURE_ROLES,
    BotAction.MENU_SCHEDULES: set(),
    BotAction.MENU_EXCEPTIONS: set(),
    BotAction.MENU_SETTINGS: set(),
    BotAction.MENU_ACCESS_RIGHTS: {Role.ADMIN.value},
    BotAction.MENU_ADMIN_PANEL: {Role.ADMIN.value},
    BotAction.TOP_SUMMARY: {Role.TOP_MANAGER.value},
    BotAction.TOP_REPORTS: {Role.TOP_MANAGER.value},
    BotAction.TOP_WORKFLOW: {Role.TOP_MANAGER.value},
    BotAction.MENU_BOT_ACTIVITY: {Role.TOP_MANAGER.value},
    BotAction.MENU_DIVISION_REPORTS: REPORT_ROLES,
    BotAction.MENU_OVERDUE_APPROVALS: MANAGER_ROLES,
    BotAction.MENU_APPROVALS: WORKFLOW_ROLES,
    BotAction.MENU_REPORTS: REPORT_ROLES,
    BotAction.MENU_SUBSTITUTIONS: WORKFLOW_ROLES,
    BotAction.SUBSTITUTION_CREATE: WORKFLOW_ROLES,
    BotAction.SUBSTITUTION_LIST: WORKFLOW_ROLES,
    BotAction.SUBSTITUTION_CANCEL: WORKFLOW_ROLES,
    BotAction.SUBSTITUTION_EXTEND: WORKFLOW_ROLES,
    BotAction.REPORT_WEEK: REPORT_ROLES,
    BotAction.REPORT_MONTH: REPORT_ROLES,
    BotAction.REPORT_QUARTER: REPORT_ROLES,
    BotAction.REPORT_CUSTOM: REPORT_ROLES,
    BotAction.REPORT_DEVICES: {Role.MANAGER.value, Role.TOP_MANAGER.value},
    BotAction.ADMIN_PERSONAL: {Role.ADMIN.value},
    BotAction.ADMIN_STRUCTURE: {Role.ADMIN.value},
    BotAction.ADMIN_SKUD: {Role.ADMIN.value},
    BotAction.ADMIN_WORKFLOW: {Role.ADMIN.value},
    BotAction.ADMIN_REPORTS: {Role.ADMIN.value},
    BotAction.ADMIN_SETTINGS: set(),
    BotAction.MENU_MY_ROW: {Role.ADMIN.value},
    BotAction.MENU_BINDING_CHECK: {Role.ADMIN.value},
}


class MaxWebhookRouter:
    def __init__(self, async_callback_outbound: bool = False, async_user_activity: bool = False) -> None:
        self.google_directory_service = GoogleSheetsDirectoryService.from_settings()
        self.employee_directory_repository = EmployeeDirectoryRepository()
        self.user_role_override_repository = UserRoleOverrideRepository()
        self.role_resolver = RoleResolver(
            google_directory_service=self.google_directory_service,
            role_override_repository=self.user_role_override_repository,
            employee_directory_repository=self.employee_directory_repository,
        )
        self.substitution_flow = SubstitutionFlowService()
        self.substitution_repository = SubstitutionRepository()
        self.case_repository = AttendanceCaseRepository()
        self.approval_repository = ApprovalRepository()
        self.google_schedule_service = GoogleSheetsScheduleService.from_settings()
        self.user_bot_activity_repository = UserBotActivityRepository()
        self.report_service = ReportService()
        self.skud_import_repository = SkudImportRepository()
        self.max_client = MaxApiClient.from_settings()
        self.delete_previous_message = get_settings().max_delete_previous_message
        self.bot_message_cursor_store = bot_message_cursor_store
        self.max_file_import_service = MaxFileImportService()
        self.office_sealing_service = OfficeSealingService(
            directory_service=self.google_directory_service,
            employee_repository=self.employee_directory_repository,
            max_client=self.max_client,
            cursor_store=self.bot_message_cursor_store,
        )
        self._directory_cache_ttl_seconds = 300
        self._directory_user_cache: dict[str, tuple[float, object]] = {}
        self._directory_name_cache: dict[str, tuple[float, object]] = {}
        self._directory_recent_cache: dict[int, tuple[float, list[object]]] = {}
        self.runtime_marker_repository = RuntimeMarkerRepository()
        self.async_callback_outbound = async_callback_outbound
        self.async_user_activity = async_user_activity
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _case_kind_label(case_type: str, source: str = "") -> str:
        if str(source or "").strip() == "forgot_chip":
            return "Забыл карточку СКУД"
        if str(source or "").strip().startswith("late_notice"):
            return "Опаздываю"
        if case_type == AttendanceCaseType.LATE.value:
            return "Опоздание"
        if case_type == AttendanceCaseType.ABSENT.value:
            return "Неявка"
        return case_type or "Случай"

    @staticmethod
    def _normalize_hhmm(value: str) -> Optional[str]:
        match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(value or ""))
        if not match:
            return None
        hours = int(match.group(1))
        minutes = int(match.group(2))
        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
            return None
        return f"{hours:02d}:{minutes:02d}"

    @staticmethod
    def _late_delay_minutes(planned_start: str, actual_start: str) -> int:
        try:
            planned = datetime.strptime(str(planned_start or ""), "%H:%M")
            actual = datetime.strptime(str(actual_start or ""), "%H:%M")
        except ValueError:
            return 0
        return max(int((actual - planned).total_seconds() // 60), 0)

    @staticmethod
    def _normalize_date(value: str) -> Optional[str]:
        raw = str(value or "").strip()
        if not raw:
            return None

        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                return datetime.strptime(raw, fmt).date().isoformat()
            except ValueError:
                continue
        return None

    @staticmethod
    def _is_date_based_notice_reason(reason_code: str) -> bool:
        return reason_code == AttendanceReasonCode.ABSENCE_NOTICE.value

    @staticmethod
    def _is_period_based_notice_reason(reason_code: str) -> bool:
        return reason_code == AttendanceReasonCode.ABSENCE_NOTICE.value

    @staticmethod
    def _build_period_reason_text(reason_label: str, date_from: str, date_to: str) -> str:
        return "{reason}. Период: {date_from} - {date_to}".format(
            reason=reason_label,
            date_from=date_from,
            date_to=date_to,
        )

    @staticmethod
    def _extract_period_bounds(reason_text: str) -> Tuple[str, str]:
        match = re.search(r"Период:\s*(\d{4}-\d{2}-\d{2})\s*-\s*(\d{4}-\d{2}-\d{2})", str(reason_text or ""))
        if not match:
            return "", ""
        return match.group(1), match.group(2)

    @staticmethod
    def _extract_period_reason_label(reason_text: str) -> str:
        raw = str(reason_text or "").strip()
        if not raw:
            return ""
        if ". Период:" in raw:
            return raw.split(". Период:", 1)[0].strip()
        return raw

    def _is_return_early_case_allowed(self, case) -> bool:
        if case is None:
            return False
        if case.case_type != AttendanceCaseType.ABSENT.value:
            return False
        if str(getattr(case, "source", "") or "") != "attendance_notice":
            return False
        date_from, date_to = self._extract_period_bounds(getattr(case, "employee_reason", ""))
        return bool(date_from and date_to and date_to >= date_from)

    def handle_event(self, payload: MaxUpdate) -> MaxWebhookResponse:
        started_at = perf_counter()
        event = self._normalize_event(payload)
        action = event["action"]
        user_text = event["text"]
        if self._is_office_seal_reminder_ack(action, user_text):
            response = self._acknowledge_office_seal_reminder(Role.EMPLOYEE.value)
            self._send_outbound(payload, response.outbound)
            self._touch_user_activity(payload, event, role="", started=False)
            return response
        role_started_at = perf_counter()
        role = self.role_resolver.resolve_role(
            user_id=event["user_id"],
            chat_id=event["chat_id"],
        )
        role_elapsed_ms = (perf_counter() - role_started_at) * 1000
        state_started_at = perf_counter()
        active_state = dialog_state_store.get(event["user_id"])
        state_elapsed_ms = (perf_counter() - state_started_at) * 1000
        self.logger.info(
            "Router event normalized update_type=%s user_id=%s chat_id=%s role=%s action=%s text_present=%s active_flow=%s role_ms=%.1f state_ms=%.1f elapsed_ms=%.1f",
            payload.update_type,
            event["user_id"],
            event["chat_id"],
            role,
            action,
            bool(user_text),
            active_state.flow if active_state else None,
            role_elapsed_ms,
            state_elapsed_ms,
            (perf_counter() - started_at) * 1000,
        )
        self._touch_user_activity(payload, event, role=role, started=self._is_start_event(payload, action, user_text))

        denied_response = self._forbidden_action_response(role, action)
        if denied_response is not None:
            self._send_outbound(payload, denied_response.outbound)
            return denied_response

        if self._is_main_menu_action(action, user_text):
            dialog_state_store.reset(event["user_id"])
            response = self._menu_response(role, "Главное меню готово.", event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if active_state and (action == BotAction.CANCEL or user_text.lower() == "отмена"):
            dialog_state_store.reset(event["user_id"])
            response = self._menu_response(role, "Действие отменено.", event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.WHOAMI or user_text in {"Обо мне", "Кто я", "/whoami"}:
            dialog_state_store.reset(event["user_id"])
            response = self._whoami(role, event["user_id"], event["chat_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if active_state and payload.update_type == "message_created" and payload.message and payload.message.body.attachments:
            file_attachments = [
                attachment
                for attachment in payload.message.body.attachments
                if self._is_supported_file_attachment(attachment)
            ]
            if active_state.flow == DialogFlow.OFFICE_SEAL_PHOTO.value:
                response = self._mark_office_sealed(role, event["user_id"])
                self._send_outbound(payload, response.outbound)
                return response
            if file_attachments and role in {
                Role.MANAGER.value,
                Role.SECURITY.value,
                Role.ADMIN.value,
                Role.TOP_MANAGER.value,
            }:
                dialog_state_store.reset(event["user_id"])
                response = self._handle_attachments(
                    role,
                    event["user_id"],
                    file_attachments,
                    message_id=payload.message.body.mid,
                )
                if response is not None:
                    self._send_outbound(payload, response.outbound)
                    return response

        if active_state and (action == BotAction.MENU_MY_LATES or user_text == "Мои опоздания"):
            dialog_state_store.reset(event["user_id"])
            response = self._employee_cases(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if active_state and active_state.flow == DialogFlow.SUBSTITUTION.value:
            result = self.substitution_flow.handle_input(event["user_id"], role, user_text, action, active_state)
            if result.completed and result.created_draft_id and result.replacement_user_id:
                self._notify_replacement_about_substitution(
                    draft_id=result.created_draft_id,
                    replacement_user_id=result.replacement_user_id,
                    target_manager=result.target_manager,
                    replacement_user=result.replacement_user,
                    date_from=result.date_from,
                    date_to=result.date_to,
                    reason=result.reason,
                    departments=result.departments,
                )
            self._send_outbound(payload, result.message)
            return MaxWebhookResponse(
                ok=True,
                role=role,
                menu=get_menu_for_role(role),
                outbound=result.message,
                active_flow=None if result.completed else active_state.flow,
            )

        if active_state and active_state.flow == DialogFlow.ATTENDANCE_REASON.value:
            response = self._handle_attendance_reason_flow(role, event["user_id"], user_text, action, active_state)
            self._send_outbound(payload, response.outbound)
            return response

        if active_state and active_state.flow == DialogFlow.FORGOT_CHIP.value:
            response = self._handle_forgot_chip_flow(role, event["user_id"], user_text, action, active_state)
            self._send_outbound(payload, response.outbound)
            return response

        if active_state and active_state.flow == DialogFlow.RUNNING_LATE.value:
            response = self._handle_running_late_flow(role, event["user_id"], user_text, action, active_state)
            self._send_outbound(payload, response.outbound)
            return response

        if active_state and active_state.flow == DialogFlow.APPROVAL_REJECTION.value:
            response = self._handle_approval_rejection_flow(role, event["user_id"], user_text, action, active_state)
            self._send_outbound(payload, response.outbound)
            return response

        if active_state and active_state.flow == DialogFlow.OFFICE_SEAL_PHOTO.value:
            response = self._mark_office_sealed(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if active_state and active_state.flow == DialogFlow.ABSENCE_PERIOD_EDIT.value:
            response = self._handle_absence_period_edit_flow(role, event["user_id"], user_text, action, active_state)
            self._send_outbound(payload, response.outbound)
            return response

        if active_state and active_state.flow == DialogFlow.REPORT_PERIOD.value:
            response = self._handle_report_period_flow(role, event["user_id"], user_text, action, active_state)
            self._send_outbound(payload, response.outbound)
            return response

        if action in {"/manager", "/employee", "/security", "/hr", "/admin", "/top"}:
            target_role = {
                "/manager": Role.MANAGER.value,
                "/employee": Role.EMPLOYEE.value,
                "/security": Role.SECURITY.value,
                "/hr": Role.HR.value,
                "/admin": Role.ADMIN.value,
                "/top": Role.TOP_MANAGER.value,
            }[action]
            self.user_role_override_repository.set_role(event["user_id"], target_role)
            self.role_resolver.clear_user_cache(event["user_id"])
            self._directory_user_cache.pop(event["user_id"], None)
            response = self._menu_response(target_role, "Роль переключена на: {0}".format(display_role_name(target_role)), event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.EMPLOYEE_PERSONAL or user_text == "Статистика":
            response = self._employee_personal_menu(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.EMPLOYEE_REASONS or user_text == "Опоздания":
            response = self._employee_reason_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.EMPLOYEE_MANAGER or (user_text == "Руководство" and role == Role.EMPLOYEE.value):
            response = self._employee_manager_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MANAGER_MANAGEMENT or (user_text == "Команда" and role == Role.MANAGER.value):
            response = self._manager_management_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MANAGER_REPORTS:
            response = self._manager_reports_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MANAGER_WORKFLOW:
            response = self._manager_workflow_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.SECURITY_SKUD or (user_text == "СКУД" and role in {Role.SECURITY.value, Role.TOP_MANAGER.value}):
            response = self._security_skud_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.HR_REFERENCE or (user_text == "Справочники" and role == Role.HR.value):
            response = self._hr_reference_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.HR_WORKFLOW or (user_text == "Процессы" and role == Role.HR.value):
            response = self._hr_workflow_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.HR_REPORTS:
            response = self._hr_reports_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.TOP_SUMMARY or (user_text == "Аналитика" and role == Role.TOP_MANAGER.value):
            response = self._top_summary_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.TOP_REPORTS:
            response = self._top_reports_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.TOP_WORKFLOW:
            response = self._top_workflow_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_MY_NOTIFICATIONS or user_text == "Мои уведомления":
            response = self._my_notifications(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_MY_LATES or user_text == "Мои опоздания":
            response = self._employee_cases(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_SUBMIT_REASON or user_text in {"Указать причину", "Объяснить опоздание", "Объяснить"}:
            response = self._employee_pending_reason_cases(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_FORGOT_CHIP or user_text in {"Забыл чип", "Забыл карточку СКУД"}:
            response = self._start_forgot_chip_flow(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_RUNNING_LATE or user_text == "Опаздываю":
            response = self._start_running_late_flow(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if (
            action.startswith(BotAction.LATE_NOTICE_MANAGER_PREFIX)
            or action.startswith(BotAction.LATE_NOTICE_DATE_PREFIX)
            or action.startswith(BotAction.LATE_NOTICE_REASON_PREFIX)
        ):
            response = self._start_running_late_flow(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action.startswith(BotAction.EMPLOYEE_REASON_START_PREFIX):
            case_id = self._parse_id(action, BotAction.EMPLOYEE_REASON_START_PREFIX)
            response = self._start_attendance_reason_flow(role, event["user_id"], case_id)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_MY_STATUSES or user_text == "Мои статусы":
            response = self._employee_case_statuses(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_MY_MANAGER or user_text == "Мой руководитель":
            response = self._my_manager(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_OFFICE_SEAL or user_text in {"Кабинет опломбирован", "🔒 Кабинет опломбирован"}:
            response = self._start_office_seal_flow(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.OFFICE_SEAL_REMINDER_ACK or user_text == "Спасибо за напоминание":
            response = self._acknowledge_office_seal_reminder(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_MY_OFFICE or user_text in {"Мой кабинет", "🚪 Мой кабинет"}:
            response = self._my_office_status(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_OFFICE_SEAL_SUMMARY or user_text in {"/статус", "Кабинеты", "Сводка кабинетов"}:
            response = self._office_seal_summary(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_EMPLOYEES or user_text == "Мои сотрудники":
            response = self._manager_employees(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_DEPARTMENT_LATES or user_text in {"Опоздания отдела", "Опоздания"}:
            response = self._department_cases(role, event["user_id"], AttendanceCaseStatus.AWAITING_EMPLOYEE_REASON.value)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_DEPARTMENT_ABSENCES or user_text in {"Неявки отдела", "Неявки отделов"}:
            if role == Role.TOP_MANAGER.value:
                response = self._top_department_absences(role)
                self._send_outbound(payload, response.outbound)
                return response
            response = self._department_cases(role, event["user_id"], AttendanceCaseStatus.NEW.value)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_SUBSTITUTIONS or user_text == "Замещения":
            response = self._substitutions_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_APPROVALS or user_text == "Согласования":
            response = self._approvals_menu(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if user_text == "Отчеты" and role == Role.TOP_MANAGER.value:
            response = self._top_reports_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if user_text == "Отчеты" and role == Role.ADMIN.value:
            response = self._admin_reports_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if user_text == "Отчеты" and role == Role.HR.value:
            response = self._hr_reports_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_REPORTS or user_text == "Отчеты":
            response = self._reports_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_SUMMARY or user_text == "Сводка":
            response = self._summary_menu(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_BOT_ACTIVITY or user_text in {"Входы", "Входы в бот"}:
            response = self._top_bot_activity(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_DIVISION_REPORTS or user_text in {"Отчеты по подразделениям", "По отделам"}:
            response = self._division_reports(role, event["user_id"], event["chat_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_OVERDUE_APPROVALS or user_text in {"Просроченные согласования", "Просроченные"}:
            response = self._overdue_approvals(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_SECURITY_IMPORT or user_text in {
            "Загрузить отчет",
            "Загрузить отчеты",
            "Загрузить выгрузку СКУД",
            "Импорт СКУД",
        }:
            response = self._security_import_help(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_IMPORT_HISTORY or user_text == "История импортов":
            response = self._security_import_history(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_STAFF or user_text == "Сотрудники":
            response = self._staff_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_DEPARTMENTS or user_text == "Подразделения":
            response = self._departments_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_ACCESS_RIGHTS or user_text == "Права доступа":
            response = self._access_rights_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_ADMIN_PANEL or user_text == "Админ-панель":
            response = self._admin_panel_menu(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.ADMIN_PERSONAL or (user_text == "Личное" and role == Role.ADMIN.value):
            response = self._admin_personal_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.ADMIN_STRUCTURE or (user_text == "Структура" and role == Role.ADMIN.value):
            response = self._admin_structure_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.ADMIN_SKUD or (user_text == "СКУД" and role == Role.ADMIN.value):
            response = self._admin_skud_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.ADMIN_WORKFLOW or (user_text == "Процессы" and role == Role.ADMIN.value):
            response = self._admin_workflow_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.ADMIN_REPORTS:
            response = self._admin_reports_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_MY_ROW or user_text == "Моя строка":
            response = self._my_row(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_BINDING_CHECK or user_text in {"Проверить привязку", "Привязка"}:
            response = self._binding_check(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.SUBSTITUTION_CREATE or user_text in {"На период", "Назначить замещение"}:
            if role not in {Role.MANAGER.value, Role.HR.value, Role.ADMIN.value, Role.TOP_MANAGER.value}:
                response = MaxWebhookResponse(
                    ok=True,
                    role=role,
                    menu=get_menu_for_role(role),
                    outbound=MaxOutboundMessage(
                        text="У тебя нет прав на назначение замещения.",
                        buttons=[MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU)],
                    ),
                    active_flow=None,
                )
                self._send_outbound(payload, response.outbound)
                return response
            result = self.substitution_flow.start(event["user_id"])
            self._send_outbound(payload, result.message)
            return MaxWebhookResponse(
                ok=True,
                role=role,
                menu=get_menu_for_role(role),
                outbound=result.message,
                active_flow=DialogFlow.SUBSTITUTION.value,
            )

        if action.startswith(BotAction.SUBSTITUTION_CANCEL_PREFIX):
            draft_id = self._parse_id(action, BotAction.SUBSTITUTION_CANCEL_PREFIX)
            response = self._cancel_substitution_draft(role, event["user_id"], draft_id)
            self._send_outbound(payload, response.outbound)
            return response

        if action.startswith(BotAction.SUBSTITUTION_OPEN_PREFIX):
            draft_id = self._parse_id(action, BotAction.SUBSTITUTION_OPEN_PREFIX)
            response = self._substitution_approval_card(role, event["user_id"], draft_id)
            self._send_outbound(payload, response.outbound)
            return response

        if action.startswith(BotAction.SUBSTITUTION_APPROVE_PREFIX):
            draft_id = self._parse_id(action, BotAction.SUBSTITUTION_APPROVE_PREFIX)
            response = self._approve_substitution_draft(role, event["user_id"], draft_id)
            self._send_outbound(payload, response.outbound)
            return response

        if action.startswith(BotAction.SUBSTITUTION_REJECT_PREFIX):
            draft_id = self._parse_id(action, BotAction.SUBSTITUTION_REJECT_PREFIX)
            response = self._reject_substitution_draft(role, event["user_id"], draft_id)
            self._send_outbound(payload, response.outbound)
            return response

        if action.startswith(BotAction.SUBSTITUTION_EXTEND_PREFIX):
            draft_id = self._parse_id(action, BotAction.SUBSTITUTION_EXTEND_PREFIX)
            response = self._start_substitution_extend_flow(role, event["user_id"], draft_id)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.SUBSTITUTION_LIST or user_text == "Мои замещения":
            response = self._substitution_list(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.SUBSTITUTION_CANCEL or user_text == "Снять замещение":
            response = self._substitution_cancel(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.SUBSTITUTION_EXTEND or user_text == "Продлить":
            response = self._substitution_extend(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if user_text == "История согласований":
            response = self._approvals_list(role, event["user_id"], action=BotAction.APPROVALS_HISTORY)
            self._send_outbound(payload, response.outbound)
            return response

        if action in {BotAction.APPROVALS_NEW, BotAction.APPROVALS_IN_PROGRESS, BotAction.APPROVALS_OVERDUE, BotAction.APPROVALS_HISTORY}:
            response = self._approvals_list(role, event["user_id"], action=action)
            self._send_outbound(payload, response.outbound)
            return response

        if action.startswith(BotAction.APPROVAL_OPEN_PREFIX):
            approval_id = self._parse_id(action, BotAction.APPROVAL_OPEN_PREFIX)
            response = self._approval_card(role, event["user_id"], approval_id)
            self._send_outbound(payload, response.outbound)
            return response

        if action.startswith(BotAction.APPROVAL_APPROVE_PREFIX):
            approval_id = self._parse_id(action, BotAction.APPROVAL_APPROVE_PREFIX)
            if self._pending_approval_for_manager(event["user_id"], approval_id) is None:
                response = self._stub_section(role, "Согласование #{0} не найдено.".format(approval_id))
                self._send_outbound(payload, response.outbound)
                return response
            approval = self.approval_repository.update_status(approval_id, ApprovalStatus.APPROVED.value)
            self._notify_employee_about_approval_decision(approval, approved=True)
            response = self._approvals_list(
                role,
                event["user_id"],
                BotAction.APPROVALS_IN_PROGRESS,
                prefix_text="Согласование #{0} подтверждено.\n\n".format(approval_id),
            )
            self._send_outbound(payload, response.outbound)
            return response

        if action.startswith(BotAction.APPROVAL_REJECT_PREFIX):
            approval_id = self._parse_id(action, BotAction.APPROVAL_REJECT_PREFIX)
            response = self._start_approval_rejection_flow(role, event["user_id"], approval_id)
            self._send_outbound(payload, response.outbound)
            return response

        if action.startswith(BotAction.EMPLOYEE_CASE_OPEN_PREFIX):
            case_id = self._parse_id(action, BotAction.EMPLOYEE_CASE_OPEN_PREFIX)
            response = self._employee_case_card(role, event["user_id"], case_id)
            self._send_outbound(payload, response.outbound)
            return response

        if action.startswith(BotAction.EMPLOYEE_CASE_RETURN_EARLY_PREFIX):
            case_id = self._parse_id(action, BotAction.EMPLOYEE_CASE_RETURN_EARLY_PREFIX)
            response = self._start_absence_period_edit_flow(role, event["user_id"], case_id)
            self._send_outbound(payload, response.outbound)
            return response

        if action.startswith(BotAction.EMPLOYEE_REASON_PREFIX):
            response = self._employee_submit_reason(role, event["user_id"], action)
            self._send_outbound(payload, response.outbound)
            return response

        if action in {BotAction.REPORT_WEEK, BotAction.REPORT_MONTH, BotAction.REPORT_QUARTER}:
            response = self._quick_report(role, event["user_id"], event["chat_id"], action)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.REPORT_CUSTOM:
            response = self._start_report_period_flow(role, event["user_id"], report_kind="manager", chat_id=event["chat_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.REPORT_DEVICES:
            response = self._device_report(role)
            self._send_outbound(payload, response.outbound)
            return response

        if payload.update_type == "message_created" and payload.message and payload.message.body.attachments:
            attachment_types = [getattr(attachment, "type", "") for attachment in payload.message.body.attachments]
            attachment_names = [getattr(attachment, "filename", "") for attachment in payload.message.body.attachments]
            self.logger.info(
                "MAX message attachments update_type=%s mid=%s types=%s filenames=%s",
                payload.update_type,
                payload.message.body.mid,
                attachment_types,
                attachment_names,
            )
            file_attachments = [
                attachment
                for attachment in payload.message.body.attachments
                if self._is_supported_file_attachment(attachment)
            ]
            if file_attachments:
                if role not in {
                    Role.MANAGER.value,
                    Role.SECURITY.value,
                    Role.ADMIN.value,
                    Role.TOP_MANAGER.value,
                }:
                    response = self._stub_section(
                        role,
                        "Загрузка файлов доступна только руководителям, службе безопасности, администраторам и главным руководителям.",
                    )
                    self._send_outbound(payload, response.outbound)
                    return response
                response = self._handle_attachments(
                    role,
                    event["user_id"],
                    payload.message.body.attachments,
                    message_id=payload.message.body.mid,
                )
                if response is not None:
                    self._send_outbound(payload, response.outbound)
                    return response
            elif not action and not user_text:
                response = MaxWebhookResponse(
                    ok=True,
                    role=role,
                    menu=get_menu_for_role(role),
                    outbound=MaxOutboundMessage(
                        text=(
                            "Я вижу вложение, но пока не умею его разобрать.\n\n"
                            "Попробуй отправить файл еще раз или скажи мне, как он выглядит в MAX."
                        ),
                        buttons=[
                            MaxOutboundButton(title="Импорт СКУД", action=BotAction.MENU_SECURITY_IMPORT),
                            MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                        ],
                    ),
                    active_flow=None,
                )
                self._send_outbound(payload, response.outbound)
                return response

        if payload.update_type == "message_callback" and action:
            dialog_state_store.reset(event["user_id"])
            response = self._menu_response(role, "Главное меню обновлено.", event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        menu = get_menu_for_role(role)
        message = MaxOutboundMessage(
            text="Не понял команду. Открой главное меню и выбери действие кнопкой.",
            buttons=self._main_menu_buttons(role, event["user_id"]),
        )
        self._send_outbound(payload, message)
        return MaxWebhookResponse(ok=True, role=role, menu=menu, outbound=message)

    def _normalize_event(self, payload: MaxUpdate) -> dict:
        if payload.update_type == "bot_started":
            return {
                "user_id": str(payload.user.user_id if payload.user else ""),
                "chat_id": str(payload.chat_id or 0),
                "text": payload.payload or "/start",
                "action": BotAction.START,
            }

        if payload.update_type == "message_callback" and payload.callback:
            return {
                "user_id": str(payload.callback.user.user_id),
                "chat_id": str(
                    payload.chat_id
                    or (payload.message.recipient.chat_id if payload.message else 0)
                ),
                "text": payload.callback.payload or "",
                "action": payload.callback.payload or "",
            }

        if payload.message:
            return {
                "user_id": str(payload.message.sender.user_id),
                "chat_id": str(payload.message.recipient.chat_id),
                "text": payload.message.body.text or "",
                "action": payload.message.body.text or "",
            }

        return {"user_id": "", "chat_id": "", "text": "", "action": ""}

    @classmethod
    def incoming_dedup_key(cls, payload: MaxUpdate) -> str:
        scope = cls._incoming_scope(payload)
        event_id = cls._incoming_event_id(payload)
        if not scope or not event_id:
            return ""
        if cls._is_start_payload(payload):
            return f"in:start:{scope}:{cls._timestamp_bucket(payload.timestamp, 60)}"
        return f"in:{payload.update_type}:{scope}:{event_id}"

    @staticmethod
    def _incoming_scope(payload: MaxUpdate) -> str:
        if payload.chat_id:
            return f"chat:{payload.chat_id}"
        if payload.callback and payload.callback.user and payload.callback.user.user_id:
            return f"user:{payload.callback.user.user_id}"
        if payload.user and payload.user.user_id:
            return f"user:{payload.user.user_id}"
        if payload.message and payload.message.sender and payload.message.sender.user_id:
            return f"user:{payload.message.sender.user_id}"
        if payload.message and payload.message.recipient and payload.message.recipient.user_id:
            return f"recipient:{payload.message.recipient.user_id}"
        return ""

    @staticmethod
    def _incoming_event_id(payload: MaxUpdate) -> str:
        if payload.callback and payload.callback.callback_id:
            return f"callback:{payload.callback.callback_id}"
        if payload.message and payload.message.body and payload.message.body.mid:
            return f"message:{payload.message.body.mid}"
        if payload.update_type == "bot_started":
            return f"start:{payload.timestamp}:{payload.payload or ''}"
        return ""

    @staticmethod
    def _timestamp_bucket(timestamp: int | float | None, seconds: int) -> int:
        value = float(timestamp or 0)
        if value > 10_000_000_000:
            value = value / 1000
        return int(value // seconds)

    @staticmethod
    def _is_start_payload(payload: MaxUpdate) -> bool:
        if payload.update_type == "bot_started":
            return True
        text = ""
        if payload.message and payload.message.body:
            text = str(payload.message.body.text or "").strip()
        return text in {BotAction.START, "Старт", "Начать"}

    @staticmethod
    def _is_start_event(payload: MaxUpdate, action: str, user_text: str) -> bool:
        if payload.update_type == "bot_started":
            return True
        normalized_action = str(action or "").strip()
        normalized_text = str(user_text or "").strip()
        return normalized_action in {BotAction.START, "Начать"} or normalized_text in {BotAction.START, "Начать"}

    @staticmethod
    def _event_display_name(payload: MaxUpdate) -> str:
        user = None
        if payload.update_type == "bot_started":
            user = payload.user
        elif payload.update_type == "message_callback" and payload.callback:
            user = payload.callback.user
        elif payload.message:
            user = payload.message.sender

        if user is None:
            return ""
        if user.name:
            return str(user.name).strip()

        first_name = str(user.first_name or "").strip()
        last_name = str(user.last_name or "").strip()
        full_name = " ".join(part for part in [first_name, last_name] if part).strip()
        if full_name:
            return full_name
        return str(user.username or "").strip()

    def _activity_display_name(self, user_id: str, fallback_name: str) -> str:
        record = self.employee_directory_repository.get_by_user_id(user_id)
        if record and record.employee_name:
            return str(record.employee_name).strip()
        return str(fallback_name or user_id).strip() or str(user_id)

    def _employee_names_for_user_id(self, user_id: str) -> List[str]:
        names: List[str] = []
        for record in (
            self.google_directory_service.get_by_user_id(user_id),
            self.employee_directory_repository.get_by_user_id(user_id),
        ):
            name = str(getattr(record, "employee_name", "") or "").strip()
            if name and name not in names:
                names.append(name)
        return names

    def _list_employee_cases_for_user(self, user_id: str, limit: int = 20):
        rows = self.case_repository.list_for_employee_user(user_id, limit=limit)
        if rows:
            return rows
        names = self._employee_names_for_user_id(user_id)
        if not names:
            return []
        return self.case_repository.list_for_employee_names(names, limit=limit)

    def _list_pending_reason_cases_for_user(self, user_id: str, limit: int = 20):
        rows = self.case_repository.list_pending_reason_for_employee(user_id, limit=limit)
        if rows:
            return rows
        names = self._employee_names_for_user_id(user_id)
        if not names:
            return []
        return self.case_repository.list_pending_reason_for_employee_names(names, limit=limit)

    @staticmethod
    def _format_dt(value: datetime | None) -> str:
        if value is None:
            return "-"
        return value.strftime("%Y-%m-%d %H:%M")

    def _menu_response(self, role: str, text: str, user_id: str = "") -> MaxWebhookResponse:
        menu = get_menu_for_role(role)
        prefix = ""
        if role == Role.ADMIN.value:
            prefix = "Администратор. Источник прав: Google Sheets.\n\n"
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=menu,
            outbound=MaxOutboundMessage(text=prefix + text, buttons=self._main_menu_buttons(role, user_id)),
            active_flow=None,
        )

    def _main_menu_buttons(self, role: str, user_id: str = "") -> list[MaxOutboundButton]:
        return list(main_menu_buttons(role))

    def _forbidden_action_response(self, role: str, action: str) -> MaxWebhookResponse | None:
        allowed_roles = ACTION_ALLOWED_ROLES.get(action)
        if allowed_roles is None or role in allowed_roles:
            return None
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Этот раздел недоступен для твоей роли.",
                buttons=[MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU)],
            ),
            active_flow=None,
        )

    def _employee_personal_menu(self, role: str, user_id: str) -> MaxWebhookResponse:
        rows = self._list_employee_cases_for_user(user_id)
        pending_reason = self._list_pending_reason_cases_for_user(user_id)
        awaiting_manager = [
            row for row in rows
            if row.status == AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value
        ]
        latest_line = "Последний статус: -"
        if rows:
            latest = rows[0]
            latest_line = "Последний статус: #{case_id} | {date} | {status}".format(
                case_id=latest.id,
                date=latest.event_date,
                status=self._status_label(latest.status),
            )
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=(
                    "Статистика сотрудника.\n\n"
                    "Всего случаев: {total}\n"
                    "Ожидают объяснение: {pending}\n"
                    "На согласовании: {awaiting}\n"
                    "{latest}"
                ).format(
                    total=len(rows),
                    pending=len(pending_reason),
                    awaiting=len(awaiting_manager),
                    latest=latest_line,
                ),
                buttons=employee_personal_buttons(),
            ),
            active_flow=None,
        )

    def _employee_reason_menu(self, role: str) -> MaxWebhookResponse:
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Раздел опозданий и объяснений.",
                buttons=employee_reason_section_buttons(),
            ),
            active_flow=None,
        )

    def _employee_manager_menu(self, role: str) -> MaxWebhookResponse:
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Раздел руководства.",
                buttons=employee_manager_section_buttons(),
            ),
            active_flow=None,
        )

    def _start_office_seal_flow(self, role: str, user_id: str) -> MaxWebhookResponse:
        return self._acknowledge_office_seal_reminder(role)

    def _acknowledge_office_seal_reminder(self, role: str) -> MaxWebhookResponse:
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=self.office_sealing_service.acknowledge_reminder(),
                buttons=[],
            ),
            active_flow=None,
        )

    @staticmethod
    def _is_office_seal_reminder_ack(action: str, user_text: str) -> bool:
        return action == BotAction.OFFICE_SEAL_REMINDER_ACK or user_text == "Спасибо за напоминание"

    def _touch_user_activity(self, payload: MaxUpdate, event: dict, role: str, started: bool) -> None:
        kwargs = {
            "user_id": event["user_id"],
            "display_name": self._event_display_name(payload),
            "role": role,
            "started": started,
        }
        if not self.async_user_activity:
            self.user_bot_activity_repository.touch(**kwargs)
            return
        threading.Thread(
            target=self._touch_user_activity_in_background,
            kwargs=kwargs,
            daemon=True,
        ).start()

    def _touch_user_activity_in_background(self, **kwargs) -> None:
        try:
            self.user_bot_activity_repository.touch(**kwargs)
        except Exception:
            self.logger.warning(
                "User bot activity background touch failed user_id=%s",
                kwargs.get("user_id"),
                exc_info=True,
            )

    def _mark_office_sealed(self, role: str, user_id: str) -> MaxWebhookResponse:
        result = self.office_sealing_service.mark_sealed(user_id=user_id)
        dialog_state_store.reset(user_id)
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=result.text,
                buttons=[MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU)],
            ),
            active_flow=None,
        )

    def _handle_office_seal_photo(
        self,
        role: str,
        user_id: str,
        attachments: List[MaxAttachment],
        *,
        message_id: str = "",
    ) -> MaxWebhookResponse:
        result = self.office_sealing_service.submit_photo(
            user_id=user_id,
            attachments=attachments,
            message_id=message_id,
        )
        if result.ok:
            dialog_state_store.reset(user_id)
            buttons = [MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU)]
        else:
            dialog_state_store.reset(user_id)
            buttons = [
                MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
            ]
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(text=result.text, buttons=buttons),
            active_flow=None,
        )

    def _office_seal_summary(self, role: str, user_id: str) -> MaxWebhookResponse:
        if role not in {Role.MANAGER.value, Role.ADMIN.value, Role.TOP_MANAGER.value}:
            text = "Сводка по опломбированию доступна руководителям."
        else:
            text = self.office_sealing_service.build_manager_summary(user_id)
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _my_office_status(self, role: str, user_id: str) -> MaxWebhookResponse:
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=self.office_sealing_service.build_employee_office_status(user_id),
                buttons=[
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _manager_management_menu(self, role: str) -> MaxWebhookResponse:
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Раздел команды: сотрудники, опоздания, неявки и сводка.",
                buttons=manager_management_buttons(),
            ),
            active_flow=None,
        )

    def _manager_reports_menu(self, role: str) -> MaxWebhookResponse:
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Раздел отчетов руководителя. Выбери нужный отчет.",
                buttons=manager_reports_buttons(),
            ),
            active_flow=None,
        )

    def _manager_workflow_menu(self, role: str) -> MaxWebhookResponse:
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Раздел процессов. Основные действия доступны через согласования и замещения.",
                buttons=manager_workflow_buttons(),
            ),
            active_flow=None,
        )

    def _security_skud_menu(self, role: str) -> MaxWebhookResponse:
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Раздел СКУД: загрузка файлов и история импортов.",
                buttons=security_skud_buttons(),
            ),
            active_flow=None,
        )

    def _hr_reference_menu(self, role: str) -> MaxWebhookResponse:
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Справочники HR.",
                buttons=hr_reference_buttons(),
            ),
            active_flow=None,
        )

    def _hr_workflow_menu(self, role: str) -> MaxWebhookResponse:
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Процессы HR.",
                buttons=hr_workflow_buttons(),
            ),
            active_flow=None,
        )

    def _hr_reports_menu(self, role: str) -> MaxWebhookResponse:
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Отчетный блок HR.",
                buttons=hr_reports_buttons(),
            ),
            active_flow=None,
        )

    def _top_summary_menu(self, role: str) -> MaxWebhookResponse:
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Аналитика верхнего уровня: сводка, просроченные согласования, отчет по подразделениям и входы в бот.",
                buttons=top_summary_buttons(),
            ),
            active_flow=None,
        )

    def _top_reports_menu(self, role: str) -> MaxWebhookResponse:
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Отчеты верхнего уровня. Выбери нужный отчет.",
                buttons=top_reports_buttons(),
            ),
            active_flow=None,
        )

    def _top_workflow_menu(self, role: str) -> MaxWebhookResponse:
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Процессы верхнего уровня.",
                buttons=top_workflow_buttons(),
            ),
            active_flow=None,
        )

    def _substitutions_menu(self, role: str) -> MaxWebhookResponse:
        buttons = substitutions_menu_buttons()
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=[button.title for button in buttons],
            outbound=MaxOutboundMessage(text="Раздел замещений на период. Выбери действие.", buttons=buttons),
            active_flow=None,
        )

    def _substitution_approval_card(self, role: str, user_id: str, draft_id: int) -> MaxWebhookResponse:
        draft = self.substitution_repository.get_draft_for_replacement(draft_id, user_id)
        if draft is None:
            return self._stub_section(role, "Запрос на замещение не найден.")

        text = (
            "Согласование замещения #{draft_id}\n\n"
            "Кого замещают: {target}\n"
            "Кто замещает: {replacement}\n"
            "Причина: {reason}\n"
            "Период: {date_from} -> {date_to}\n"
            "Курируемые отделы: {departments}\n"
            "Статус: {status}"
        ).format(
            draft_id=draft.id,
            target=draft.target_manager,
            replacement=draft.replacement_user,
            reason=draft.reason,
            date_from=draft.date_from,
            date_to=draft.date_to,
            departments=self._substitution_departments_label(getattr(draft, "departments_json", "[]")),
            status=self._substitution_status_label(draft.status),
        )
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(text=text, buttons=substitution_approval_card_buttons(draft.id)),
            active_flow=None,
        )

    def _approvals_menu(self, role: str, user_id: str) -> MaxWebhookResponse:
        buttons = approvals_menu_buttons()
        pending = self.approval_repository.list_pending_for_manager(user_id)
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=[button.title for button in buttons],
            outbound=MaxOutboundMessage(
                text="Раздел согласований. Ожидают решения: {count}".format(count=len(pending)),
                buttons=buttons,
            ),
            active_flow=None,
        )

    def _reports_menu(self, role: str) -> MaxWebhookResponse:
        buttons = reports_menu_buttons()
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=[button.title for button in buttons],
            outbound=MaxOutboundMessage(text="Раздел отчетов. Выбери период.", buttons=buttons),
            active_flow=None,
        )

    def _security_import_help(self, role: str, user_id: str) -> MaxWebhookResponse:
        text = "Отправь файл с проходами прямо сюда, и я сам его разберу.\n\nПодойдут файлы в формате CSV или Excel."
        back_action = self._skud_back_action(role)
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="История импортов", action=BotAction.MENU_IMPORT_HISTORY),
                    MaxOutboundButton(title="Назад", action=back_action),
                ],
            ),
            active_flow=None,
        )

    def _security_import_history(self, role: str) -> MaxWebhookResponse:
        rows = self.skud_import_repository.list_recent(limit=8)
        if not rows:
            text = "Пока нет загруженных файлов."
        else:
            text = "Последние загрузки:\n\n" + "\n".join(
                "#{id} | {filename} | {period_start} - {period_end} | сотрудников: {employees} | случаев: {created} | ошибок: {errors} | {status}".format(
                    id=row.id,
                    filename=row.filename,
                    period_start=row.period_start or "-",
                    period_end=row.period_end or "-",
                    employees=row.unique_employees,
                    created=row.created_cases,
                    errors=row.error_rows,
                    status=row.status,
                )
                for row in rows
            )

        back_action = self._skud_back_action(role)
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[MaxOutboundButton(title="Назад", action=back_action)],
            ),
            active_flow=None,
        )

    def _my_notifications(self, role: str, user_id: str) -> MaxWebhookResponse:
        rows = self.case_repository.list_for_employee_user(user_id)
        pending_reason = self.case_repository.list_pending_reason_for_employee(user_id)
        if not rows:
            text = (
                "У тебя пока нет уведомлений.\n\n"
                "Если справочник сотрудников еще не загружен, импортируй его через раздел `Сотрудники`."
            )
        else:
            latest = rows[0]
            text = (
                "Уведомления по твоим случаям:\n\n"
                "Всего случаев: {total}\n"
                "Ожидают причину: {pending}\n"
                "Последний статус: #{case_id} | {date} | {status}"
            ).format(
                total=len(rows),
                pending=len(pending_reason),
                case_id=latest.id,
                date=latest.event_date,
                status=self._status_label(latest.status),
            )

        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Назад", action=BotAction.EMPLOYEE_MANAGER),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _my_manager(self, role: str, user_id: str) -> MaxWebhookResponse:
        record = self._resolve_directory_record_by_user_id(user_id)
        if record is not None and record.manager_name:
            text = (
                "Твой руководитель:\n\n"
                "ФИО: {manager}\n"
                "Подразделение: {department}\n"
                "Роль: {role}"
            ).format(
                manager=record.manager_name,
                department=record.department_name or "-",
                role=display_role_name(record.role or "employee"),
            )
        else:
            cases = self.case_repository.list_for_employee_user(user_id)
            manager_name = cases[0].manager_name if cases and cases[0].manager_name else ""
            if manager_name:
                text = "Твой руководитель: {0}".format(manager_name)
            else:
                text = "Данные о руководителе пока не загружены."

        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Назад", action=BotAction.EMPLOYEE_MANAGER),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _manager_employees(self, role: str, user_id: str) -> MaxWebhookResponse:
        directory_rows = self._resolve_directory_rows_by_manager_user_id(user_id)
        directory_rows = self._merge_by_key(
            directory_rows,
            self._resolve_directory_rows_by_curated_departments(user_id),
            key_name="employee_user_id",
        )
        if directory_rows:
            lines = [
                "#{id} | {name} | {dept} | {status}".format(
                    id=row.id,
                    name=row.employee_name,
                    dept=row.department_name or "-",
                    status="активен" if row.is_active else "не активен",
                )
                for row in directory_rows[:10]
            ]
            text = "Твои сотрудники:\n\n" + "\n".join(lines)
        else:
            case_rows = self._manager_case_rows(user_id, limit=10)
            if case_rows:
                unique_employees = []
                seen = set()
                for case in case_rows:
                    if case.employee_name in seen:
                        continue
                    seen.add(case.employee_name)
                    unique_employees.append(case.employee_name)
                text = "Твои сотрудники по случаям:\n\n" + "\n".join(f"- {name}" for name in unique_employees[:10])
            else:
                text = "Сотрудники пока не загружены."

        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Согласования", action=BotAction.MENU_APPROVALS),
                    MaxOutboundButton(title="Опоздания", action=BotAction.MENU_DEPARTMENT_LATES),
                    MaxOutboundButton(title="Назад", action=BotAction.MANAGER_MANAGEMENT),
                ],
            ),
            active_flow=None,
        )

    def _department_cases(self, role: str, user_id: str, status_hint: str) -> MaxWebhookResponse:
        rows = self._manager_case_rows(user_id, limit=20)
        if not rows:
            text = "По твоим сотрудникам пока нет случаев."
        else:
            if status_hint == AttendanceCaseStatus.AWAITING_EMPLOYEE_REASON.value:
                filtered = [case for case in rows if case.case_type == "late"]
                title = "Опоздания отдела"
            else:
                filtered = [case for case in rows if case.case_type == "absent"]
                title = "Неявки отдела"

            if not filtered:
                text = f"{title} пока нет."
            else:
                lines = [
                    "#{id} | {employee} | {date} | {status}".format(
                        id=case.id,
                        employee=case.employee_name,
                        date=case.event_date,
                        status=self._status_label(case.status),
                    )
                    for case in filtered[:10]
                ]
                text = f"{title}:\n\n" + "\n".join(lines)

        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Согласования", action=BotAction.MENU_APPROVALS),
                    MaxOutboundButton(title="Отчеты", action=BotAction.MANAGER_REPORTS),
                    MaxOutboundButton(title="Назад", action=BotAction.MANAGER_MANAGEMENT),
                ],
            ),
            active_flow=None,
        )

    def _top_department_absences(self, role: str) -> MaxWebhookResponse:
        rows = [
            case
            for case in self.case_repository.list_all(limit=5000)
            if getattr(case, "case_type", "") == AttendanceCaseType.ABSENT.value
        ]
        if not rows:
            text = "Неявок по отделам за весь период пока нет."
        else:
            counts: dict[str, int] = {}
            for case in rows:
                department = getattr(case, "department_name", "") or "Не указано"
                counts[department] = counts.get(department, 0) + 1
            lines = [
                f"- {department}: {count}"
                for department, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:20]
            ]
            text = "Неявки отделов за весь период:\n\nВсего: {total}\n\n{lines}".format(
                total=len(rows),
                lines="\n".join(lines),
            )

        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Назад", action=BotAction.TOP_SUMMARY),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _summary_menu(self, role: str, user_id: str) -> MaxWebhookResponse:
        approvals = len(self._manager_approval_rows(user_id, statuses=[ApprovalStatus.PENDING.value], limit=500))
        cases = len(
            self._manager_case_rows(
                user_id,
                statuses=[
                    AttendanceCaseStatus.AWAITING_EMPLOYEE_REASON.value,
                    AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value,
                ],
                limit=500,
            )
        )
        text = (
            "Сводка:\n\n"
            "Ожидают согласования: {approvals}\n"
            "Активных случаев по твоим сотрудникам: {cases}"
        ).format(approvals=approvals, cases=cases)
        back_action = BotAction.TOP_SUMMARY if role == Role.TOP_MANAGER.value else BotAction.MANAGER_MANAGEMENT
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Просроченные", action=BotAction.MENU_OVERDUE_APPROVALS),
                    MaxOutboundButton(title="По отделам", action=BotAction.MENU_DIVISION_REPORTS),
                    MaxOutboundButton(title="Устройства", action=BotAction.REPORT_DEVICES),
                    MaxOutboundButton(title="Назад", action=back_action),
                ],
            ),
            active_flow=None,
        )

    def _top_bot_activity(self, role: str) -> MaxWebhookResponse:
        if role != Role.TOP_MANAGER.value:
            return self._stub_section(role, "Раздел доступен только главному руководителю.")

        now = utc_now()
        seen_total = self.user_bot_activity_repository.count_seen_total()
        started_total = self.user_bot_activity_repository.count_started_total()
        started_week = self.user_bot_activity_repository.count_started_since(now - timedelta(days=7))
        active_week = self.user_bot_activity_repository.count_active_since(now - timedelta(days=7))
        rows = self.user_bot_activity_repository.list_recent_seen(limit=10)
        device_counts = {"Android": 0, "iOS": 0, "неизвестно": 0}
        for row in rows:
            device_counts[self._display_device_platform(getattr(row, "device_platform", ""))] += 1

        lines = [
            "Входы в бот:\n",
            f"Вообще были в боте: {seen_total}",
            f"Взаимодействовали за 7 дней: {active_week}",
            f"Запускали бот за 7 дней: {started_week}",
            f"Запускали бот всего: {started_total}",
            f"Устройства в последних {len(rows)}: Android: {device_counts['Android']}, iOS: {device_counts['iOS']}, неизвестно: {device_counts['неизвестно']}",
        ]

        if rows:
            lines.append("")
            lines.append("Последняя активность:")
            for row in rows:
                name = self._activity_display_name(row.user_id, row.display_name)
                role_label = display_role_name(str(row.role or "employee"))
                device = self._display_device_platform(getattr(row, "device_platform", ""))
                lines.append(f"{name} | {role_label} | {device} | {self._format_dt(row.last_seen_at)}")
        else:
            lines.append("")
            lines.append("Пока никто не взаимодействовал с ботом.")

        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="\n".join(lines),
                buttons=[
                    MaxOutboundButton(title="Сводка", action=BotAction.MENU_SUMMARY),
                    MaxOutboundButton(title="По отделам", action=BotAction.MENU_DIVISION_REPORTS),
                    MaxOutboundButton(title="Назад", action=BotAction.TOP_SUMMARY),
                ],
            ),
            active_flow=None,
        )

    def _device_report(self, role: str) -> MaxWebhookResponse:
        if role not in {Role.MANAGER.value, Role.TOP_MANAGER.value}:
            return self._stub_section(role, "Отчет доступен руководителям.")

        counts = self.user_bot_activity_repository.count_by_device_platform()
        android = int(counts.get("android", 0) or 0)
        ios = int(counts.get("ios", 0) or 0)
        unknown = int(counts.get("unknown", 0) or 0)
        total = android + ios + unknown
        detected = android + ios
        back_action = BotAction.TOP_REPORTS if role == Role.TOP_MANAGER.value else BotAction.MANAGER_REPORTS
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=(
                    "Устройства пользователей:\n\n"
                    f"Android: {android}\n"
                    f"iOS: {ios}\n"
                    f"Неизвестно: {unknown}\n"
                    f"Определили устройство: {detected}\n"
                    f"Всего пользователей: {total}"
                ),
                buttons=[
                    MaxOutboundButton(title="Назад", action=back_action),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _division_reports(self, role: str, user_id: str, chat_id: str) -> MaxWebhookResponse:
        return self._start_report_period_flow(role, user_id, report_kind="division", chat_id=chat_id)

    def _overdue_approvals(self, role: str, user_id: str) -> MaxWebhookResponse:
        rows = self.approval_repository.list_overdue_for_manager(user_id)
        if not rows:
            text = "Просроченных согласований нет."
            buttons = [MaxOutboundButton(title="Назад", action=BotAction.MENU_APPROVALS)]
        else:
            lines = [
                "#{approval_id} | {employee} | {date} | {kind}".format(
                    approval_id=approval.id,
                    employee=case.employee_name,
                    date=case.event_date,
                    kind=self._case_kind_label(case.case_type, getattr(case, "source", "")),
                )
                for approval, case in rows[:10]
            ]
            text = "Просроченные согласования:\n\n" + "\n".join(lines)
            buttons = [
                MaxOutboundButton(title="Согласования", action=BotAction.MENU_APPROVALS),
                MaxOutboundButton(title="Назад", action=BotAction.MANAGER_REPORTS),
            ]

        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(text=text, buttons=buttons),
            active_flow=None,
        )

    def _quick_report(self, role: str, user_id: str, chat_id: str, action: str) -> MaxWebhookResponse:
        label = {
            BotAction.REPORT_WEEK: "недельный",
            BotAction.REPORT_MONTH: "месячный",
            BotAction.REPORT_QUARTER: "квартальный",
        }.get(action, "выбранный")
        period = {
            BotAction.REPORT_WEEK: "week",
            BotAction.REPORT_MONTH: "month",
            BotAction.REPORT_QUARTER: "quarter",
        }.get(action, "week")
        self._queue_manager_report(chat_id=chat_id, user_id=user_id, role=role, period=period)
        text = "{title} отчет формируется. Пришлю файлы отдельным сообщением.".format(title=label.capitalize())
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Сводка", action=BotAction.MENU_SUMMARY),
                    MaxOutboundButton(title="По отделам", action=BotAction.MENU_DIVISION_REPORTS),
                    MaxOutboundButton(title="Назад", action=BotAction.MANAGER_REPORTS),
                ],
            ),
            active_flow=None,
        )

    def _report_menu_response(self, role: str) -> MaxWebhookResponse:
        if role == Role.MANAGER.value:
            return self._manager_reports_menu(role)
        if role == Role.TOP_MANAGER.value:
            return self._top_reports_menu(role)
        if role == Role.ADMIN.value:
            return self._admin_reports_menu(role)
        return self._reports_menu(role)

    @staticmethod
    def _report_back_action(role: str) -> str:
        if role == Role.MANAGER.value:
            return BotAction.MANAGER_REPORTS
        if role == Role.TOP_MANAGER.value:
            return BotAction.TOP_REPORTS
        if role == Role.ADMIN.value:
            return BotAction.ADMIN_REPORTS
        if role == Role.HR.value:
            return BotAction.HR_REPORTS
        return BotAction.MENU_REPORTS

    @staticmethod
    def _skud_back_action(role: str) -> str:
        if role == Role.MANAGER.value:
            return BotAction.MANAGER_REPORTS
        if role == Role.ADMIN.value:
            return BotAction.ADMIN_SKUD
        return BotAction.SECURITY_SKUD

    @staticmethod
    def _structure_back_action(role: str) -> str:
        if role == Role.ADMIN.value:
            return BotAction.ADMIN_STRUCTURE
        return BotAction.HR_REFERENCE

    def _start_report_period_flow(self, role: str, user_id: str, report_kind: str, chat_id: str = "") -> MaxWebhookResponse:
        dialog_state_store.set(
            user_id,
            UserDialogState(
                flow=DialogFlow.REPORT_PERIOD.value,
                step="enter_date_from",
                data={"report_kind": report_kind, "chat_id": str(chat_id or "")},
            ),
        )
        title = "отчета по подразделениям" if report_kind == "division" else "отчета"
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=(
                    "Выбери период для {title}.\n\n"
                    "Введи дату начала в формате `ДД.ММ.ГГГГ` или `ГГГГ-ММ-ДД`."
                ).format(title=title),
                buttons=[
                    MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                ],
            ),
            active_flow=DialogFlow.REPORT_PERIOD.value,
        )

    def _handle_report_period_flow(
        self,
        role: str,
        user_id: str,
        user_text: str,
        action: str,
        state: UserDialogState,
    ) -> MaxWebhookResponse:
        report_kind = state.data.get("report_kind", "manager")
        if action == BotAction.BACK or user_text == "Назад":
            if state.step == "enter_date_to":
                state.step = "enter_date_from"
                dialog_state_store.set(user_id, state)
                return MaxWebhookResponse(
                    ok=True,
                    role=role,
                    menu=get_menu_for_role(role),
                    outbound=MaxOutboundMessage(
                        text="Введи дату начала периода в формате `ДД.ММ.ГГГГ` или `ГГГГ-ММ-ДД`.",
                        buttons=[
                            MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                            MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                        ],
                    ),
                    active_flow=DialogFlow.REPORT_PERIOD.value,
                )
            dialog_state_store.reset(user_id)
            return self._report_menu_response(role)

        if state.step == "enter_date_from":
            date_from = self._normalize_date(user_text)
            if date_from is None:
                return MaxWebhookResponse(
                    ok=True,
                    role=role,
                    menu=get_menu_for_role(role),
                    outbound=MaxOutboundMessage(
                        text="Не понял дату начала. Введи ее в формате `ДД.ММ.ГГГГ` или `ГГГГ-ММ-ДД`.",
                        buttons=[
                            MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                            MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                        ],
                    ),
                    active_flow=DialogFlow.REPORT_PERIOD.value,
                )
            state.step = "enter_date_to"
            state.data["date_from"] = date_from
            dialog_state_store.set(user_id, state)
            return MaxWebhookResponse(
                ok=True,
                role=role,
                menu=get_menu_for_role(role),
                outbound=MaxOutboundMessage(
                    text=(
                        "Дата начала: {date_from}\n\n"
                        "Теперь введи дату окончания в формате `ДД.ММ.ГГГГ` или `ГГГГ-ММ-ДД`."
                    ).format(date_from=date_from),
                    buttons=[
                        MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                        MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                    ],
                ),
                active_flow=DialogFlow.REPORT_PERIOD.value,
            )

        if state.step == "enter_date_to":
            date_to = self._normalize_date(user_text)
            if date_to is None:
                return MaxWebhookResponse(
                    ok=True,
                    role=role,
                    menu=get_menu_for_role(role),
                    outbound=MaxOutboundMessage(
                        text="Не понял дату окончания. Введи ее в формате `ДД.ММ.ГГГГ` или `ГГГГ-ММ-ДД`.",
                        buttons=[
                            MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                            MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                        ],
                    ),
                    active_flow=DialogFlow.REPORT_PERIOD.value,
                )
            date_from = state.data.get("date_from", "")
            chat_id = state.data.get("chat_id", "")
            if date_from and date_to < date_from:
                return MaxWebhookResponse(
                    ok=True,
                    role=role,
                    menu=get_menu_for_role(role),
                    outbound=MaxOutboundMessage(
                        text=(
                            "Дата окончания не может быть раньше даты начала.\n\n"
                            "Дата начала: {date_from}\n"
                            "Введи дату окончания заново."
                        ).format(date_from=date_from),
                        buttons=[
                            MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                            MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                        ],
                    ),
                    active_flow=DialogFlow.REPORT_PERIOD.value,
                )
            dialog_state_store.reset(user_id)
            if report_kind == "division":
                self._queue_division_report(
                    chat_id=chat_id,
                    user_id=user_id,
                    role=role,
                    period="custom",
                    date_from=date_from,
                    date_to=date_to,
                )
                text = (
                    "Отчет по подразделениям за период формируется.\n\n"
                    "Период: {date_from} - {date_to}\n"
                    "Пришлю файлы отдельным сообщением."
                ).format(date_from=date_from, date_to=date_to)
            else:
                self._queue_manager_report(
                    chat_id=chat_id,
                    user_id=user_id,
                    role=role,
                    period="custom",
                    date_from=date_from,
                    date_to=date_to,
                )
                text = (
                    "Отчет за период формируется.\n\n"
                    "Период: {date_from} - {date_to}\n"
                    "Пришлю файлы отдельным сообщением."
                ).format(date_from=date_from, date_to=date_to)
            return MaxWebhookResponse(
                ok=True,
                role=role,
                menu=get_menu_for_role(role),
                outbound=MaxOutboundMessage(
                    text=text,
                    buttons=[
                        MaxOutboundButton(title="По отделам", action=BotAction.MENU_DIVISION_REPORTS, emoji="🏢", row=0),
                        MaxOutboundButton(title="Назад", action=self._report_back_action(role), emoji="↩️", row=1),
                    ],
                ),
                active_flow=None,
            )

        dialog_state_store.reset(user_id)
        return self._report_menu_response(role)

    def _substitution_cancel(self, role: str, user_id: str) -> MaxWebhookResponse:
        rows = self.substitution_repository.list_drafts_for_user(user_id)
        if not rows:
            text = "У тебя нет замещений для снятия."
        else:
            lines = [
                "#{id} | {target} -> {replacement} | {date_from} - {date_to} | {status}".format(
                    id=row.id,
                    target=row.target_manager,
                    replacement=row.replacement_user,
                    date_from=row.date_from,
                    date_to=row.date_to,
                    status=row.status,
                )
                for row in rows[:5]
            ]
            text = "Выбери замещение для снятия:\n\n" + "\n".join(lines)
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=self._substitution_draft_action_buttons(rows, mode="cancel"),
            ),
            active_flow=None,
        )

    def _approve_substitution_draft(self, role: str, user_id: str, draft_id: int) -> MaxWebhookResponse:
        if draft_id <= 0:
            return self._stub_section(role, "Запрос на замещение не найден.")
        draft = self.substitution_repository.approve_draft(draft_id, user_id)
        if draft is None:
            return self._stub_section(role, "Запрос на замещение не найден или недоступен.")
        self._notify_initiator_about_substitution_decision(draft, approved=True)
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Ты согласовал замещение #{0}.\n\nПериод: {1} -> {2}".format(
                    draft.id,
                    draft.date_from,
                    draft.date_to,
                ),
                buttons=[
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _reject_substitution_draft(self, role: str, user_id: str, draft_id: int) -> MaxWebhookResponse:
        if draft_id <= 0:
            return self._stub_section(role, "Запрос на замещение не найден.")
        draft = self.substitution_repository.reject_draft(draft_id, user_id)
        if draft is None:
            return self._stub_section(role, "Запрос на замещение не найден или недоступен.")
        self._notify_initiator_about_substitution_decision(draft, approved=False)
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Ты отклонил замещение #{0}.".format(draft.id),
                buttons=[
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _substitution_extend(self, role: str, user_id: str) -> MaxWebhookResponse:
        rows = self.substitution_repository.list_drafts_for_user(user_id)
        if not rows:
            text = "У тебя нет замещений для продления."
        else:
            lines = [
                "#{id} | {target} -> {replacement} | {date_from} - {date_to} | {status}".format(
                    id=row.id,
                    target=row.target_manager,
                    replacement=row.replacement_user,
                    date_from=row.date_from,
                    date_to=row.date_to,
                    status=row.status,
                )
                for row in rows[:5]
            ]
            text = "Выбери черновик для продления:\n\n" + "\n".join(lines)
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=self._substitution_draft_action_buttons(rows, mode="extend"),
            ),
            active_flow=None,
        )

    def _staff_menu(self, role: str) -> MaxWebhookResponse:
        rows = self._resolve_directory_rows_recent(limit=8)
        if not rows:
            text = (
                "Список сотрудников пока пустой.\n\n"
                "Как только он будет загружен, я покажу его здесь."
            )
        else:
            text = "Последние сотрудники:\n\n" + "\n".join(
                "#{id} | {name} | {user_id} | {role} | {dept}".format(
                    id=row.id,
                    name=row.employee_name,
                    user_id=row.employee_user_id,
                    role=display_role_name(row.role),
                    dept=row.department_name or "-",
                )
                for row in rows
            )

        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Подразделения", action=BotAction.MENU_DEPARTMENTS),
                    MaxOutboundButton(title="Назад", action=self._structure_back_action(role)),
                ],
            ),
            active_flow=None,
        )

    def _departments_menu(self, role: str) -> MaxWebhookResponse:
        rows = self._resolve_directory_rows_recent(limit=100)
        departments = {}
        for row in rows:
            if not row.department_name:
                continue
            departments.setdefault(row.department_name, 0)
            departments[row.department_name] += 1
        if not departments:
            text = (
                "Подразделения пока не загружены.\n\n"
                "Они появятся после загрузки списка сотрудников."
            )
        else:
            lines = [f"- {name}: {count}" for name, count in sorted(departments.items())]
            text = "Подразделения:\n\n" + "\n".join(lines)
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Сотрудники", action=BotAction.MENU_STAFF),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _resolve_directory_record_by_user_id(self, user_id: str, *, refresh_on_miss: bool = False):
        normalized_user_id = str(user_id or "").strip()
        cached_record = self._cached_directory_user(normalized_user_id)
        if cached_record is not None:
            return cached_record
        local_record = self.employee_directory_repository.get_by_user_id(normalized_user_id)
        if local_record is not None:
            self._remember_directory_user(normalized_user_id, local_record)
            return local_record
        google_record = self.google_directory_service.get_by_user_id(normalized_user_id)
        if google_record is None and refresh_on_miss:
            google_record = self.google_directory_service.get_by_user_id(normalized_user_id, refresh=True)
        if google_record is not None:
            self._remember_directory_user(normalized_user_id, google_record)
            return google_record
        return None

    def _resolve_directory_record_by_employee_name(self, employee_name: str):
        normalized_name = str(employee_name or "").strip()
        cached_record = self._cached_directory_name(normalized_name)
        if cached_record is not None:
            return cached_record
        local_record = self.employee_directory_repository.get_by_employee_name(normalized_name)
        if local_record is not None:
            self._remember_directory_name(normalized_name, local_record)
            return local_record
        google_record = self.google_directory_service.get_by_employee_name(normalized_name)
        if google_record is not None:
            self._remember_directory_name(normalized_name, google_record)
        return google_record

    def _resolve_directory_rows_by_manager_user_id(self, manager_user_id: str):
        local_rows = self.employee_directory_repository.get_by_manager_user_id(manager_user_id)
        if local_rows:
            return local_rows
        return self.google_directory_service.get_by_manager_user_id(manager_user_id)

    def _resolve_directory_rows_by_curated_departments(self, user_id: str):
        departments = self._active_curated_departments(user_id)
        if not departments:
            return []
        local_rows = self.employee_directory_repository.list_by_department_names(departments)
        if local_rows:
            return local_rows
        return [
            row
            for row in self.google_directory_service.list_employees()
            if getattr(row, "is_active", True) and getattr(row, "department_name", "") in departments
        ]

    def _active_curated_departments(self, user_id: str, *, date_from: str = "", date_to: str = "") -> List[str]:
        period_start = date_from or datetime.now().date().isoformat()
        period_end = date_to or period_start
        drafts = self.substitution_repository.list_approved_overlapping(period_start, period_end)
        departments: List[str] = []
        seen: set[str] = set()
        for draft in drafts:
            if getattr(draft, "replacement_user_id", "") != user_id:
                continue
            for department in self.substitution_repository.departments_for_draft(draft):
                if department not in seen:
                    seen.add(department)
                    departments.append(department)
        return departments

    @staticmethod
    def _merge_by_key(primary, secondary, *, key_name: str):
        merged = []
        seen: set[str] = set()
        for row in list(primary or []) + list(secondary or []):
            key = str(getattr(row, key_name, "") or getattr(row, "id", "") or id(row))
            if key in seen:
                continue
            seen.add(key)
            merged.append(row)
        return merged

    def _manager_case_rows(self, user_id: str, statuses: List[str] | None = None, limit: int = 500):
        direct = self.case_repository.list_for_manager_user(user_id, limit=limit)
        if statuses:
            direct = [row for row in direct if row.status in statuses]
        curated = self.case_repository.list_for_department_names(
            self._active_curated_departments(user_id),
            statuses=statuses,
            limit=limit,
        )
        return self._merge_by_key(direct, curated, key_name="id")[:limit]

    def _manager_approval_rows(self, user_id: str, statuses: List[str] | None = None, limit: int = 500):
        direct = self.approval_repository.list_for_manager(user_id, statuses=statuses, limit=limit)
        curated = self.approval_repository.list_for_department_names(
            self._active_curated_departments(user_id),
            statuses=statuses,
            limit=limit,
        )
        merged = []
        seen: set[str] = set()
        for approval, case in list(direct or []) + list(curated or []):
            key = str(getattr(approval, "id", ""))
            if key in seen:
                continue
            seen.add(key)
            merged.append((approval, case))
        return merged[:limit]

    def _manager_overdue_approval_rows(self, user_id: str, limit: int = 20):
        direct = self.approval_repository.list_overdue_for_manager(user_id, limit=limit)
        curated_pending = self.approval_repository.list_for_department_names(
            self._active_curated_departments(user_id),
            statuses=[ApprovalStatus.PENDING.value],
            limit=500,
        )
        overdue_before = utc_now() - timedelta(days=2)
        curated = [
            (approval, case)
            for approval, case in curated_pending
            if getattr(approval, "created_at", utc_now()) <= overdue_before
        ]
        merged = []
        seen: set[str] = set()
        for approval, case in direct + curated:
            key = str(getattr(approval, "id", ""))
            if key in seen:
                continue
            seen.add(key)
            merged.append((approval, case))
        return merged[:limit]

    def _resolve_directory_rows_recent(self, limit: int = 50):
        cached_rows = self._cached_directory_rows_recent(limit)
        if cached_rows:
            return cached_rows
        local_rows = self.employee_directory_repository.list_recent(limit=limit)
        if local_rows:
            self._remember_directory_rows_recent(limit, local_rows)
            return local_rows
        google_rows = self.google_directory_service.list_employees()[:limit]
        self._remember_directory_rows_recent(limit, google_rows)
        return google_rows

    def _cached_directory_user(self, user_id: str):
        cached = self._directory_user_cache.get(user_id)
        if not cached:
            return None
        expires_at, record = cached
        if expires_at <= monotonic():
            self._directory_user_cache.pop(user_id, None)
            return None
        return record

    def _remember_directory_user(self, user_id: str, record) -> None:
        if user_id and record is not None:
            self._directory_user_cache[user_id] = (monotonic() + self._directory_cache_ttl_seconds, record)
            employee_name = str(getattr(record, "employee_name", "") or "").strip()
            if employee_name:
                self._remember_directory_name(employee_name, record)

    def _cached_directory_name(self, employee_name: str):
        cached = self._directory_name_cache.get(employee_name)
        if not cached:
            return None
        expires_at, record = cached
        if expires_at <= monotonic():
            self._directory_name_cache.pop(employee_name, None)
            return None
        return record

    def _remember_directory_name(self, employee_name: str, record) -> None:
        if employee_name and record is not None:
            self._directory_name_cache[employee_name] = (monotonic() + self._directory_cache_ttl_seconds, record)
            user_id = str(getattr(record, "employee_user_id", "") or "").strip()
            if user_id:
                self._directory_user_cache[user_id] = (monotonic() + self._directory_cache_ttl_seconds, record)

    def _cached_directory_rows_recent(self, limit: int):
        cached = self._directory_recent_cache.get(limit)
        if not cached:
            return []
        expires_at, rows = cached
        if expires_at <= monotonic():
            self._directory_recent_cache.pop(limit, None)
            return []
        return list(rows)

    def _remember_directory_rows_recent(self, limit: int, rows) -> None:
        self._directory_recent_cache[limit] = (monotonic() + self._directory_cache_ttl_seconds, list(rows or []))

    def _access_rights_menu(self, role: str) -> MaxWebhookResponse:
        if role != Role.ADMIN.value:
            return self._stub_section(role, "Раздел прав доступа доступен только администратору.")

        overrides = self.user_role_override_repository.list_all(limit=20)
        if not overrides:
            rows_text = "Override-ролей пока нет."
        else:
            rows_text = "\n".join(
                "#{id} | {user_id} | {role} | {updated_at}".format(
                    id=row.id,
                    user_id=row.user_id,
                    role=display_role_name(row.role),
                    updated_at=row.updated_at.isoformat(timespec="seconds"),
                )
                for row in overrides
            )

        text = (
            "Права доступа администратора:\n\n"
            "Доступны все разделы сотрудника, руководителя, безопасности и HR.\n"
            "Администратор может просматривать, импортировать, согласовывать и управлять замещениями.\n\n"
            "Текущие override-роли:\n{rows}"
        ).format(rows=rows_text)
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Сотрудники", action=BotAction.MENU_STAFF),
                    MaxOutboundButton(title="История импортов", action=BotAction.MENU_IMPORT_HISTORY),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _admin_panel_menu(self, role: str, user_id: str) -> MaxWebhookResponse:
        if role != Role.ADMIN.value:
            return self._stub_section(role, "Админ-панель доступна только администратору.")

        sheet_record = self.google_directory_service.get_by_user_id(user_id)
        if not self._google_directory_is_configured():
            directory_state = "Google Sheets не настроен в текущей runtime-среде"
        else:
            directory_state = "найдено в Google Sheets" if sheet_record else "не найдено в Google Sheets"
        text = (
            "Админ-панель:\n\n"
            "Текущая роль: {role}\n"
            "Профиль в таблице: {directory_state}\n\n"
            "Если ты видишь это меню, значит доступ к админскому интерфейсу уже выдан.\n"
            "Личный, структурный, СКУД и отчетный разделы теперь открываются отдельными кнопками, чтобы экран не был перегружен."
        ).format(directory_state=directory_state, role=display_role_name(role))
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=main_menu_buttons(role),
            ),
            active_flow=None,
        )

    def _admin_personal_menu(self, role: str) -> MaxWebhookResponse:
        if role != Role.ADMIN.value:
            return self._stub_section(role, "Личный раздел администратора доступен только администратору.")
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Личный раздел администратора. Здесь быстрые проверки и привязки.",
                buttons=admin_personal_buttons(),
            ),
            active_flow=None,
        )

    def _admin_structure_menu(self, role: str) -> MaxWebhookResponse:
        if role != Role.ADMIN.value:
            return self._stub_section(role, "Раздел структуры доступен только администратору.")
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Структура и справочники.",
                buttons=admin_structure_buttons(),
            ),
            active_flow=None,
        )

    def _admin_skud_menu(self, role: str) -> MaxWebhookResponse:
        if role != Role.ADMIN.value:
            return self._stub_section(role, "Раздел СКУД доступен только администратору.")
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Импорт СКУД и очереди разборов.",
                buttons=admin_skud_buttons(),
            ),
            active_flow=None,
        )

    def _admin_workflow_menu(self, role: str) -> MaxWebhookResponse:
        if role != Role.ADMIN.value:
            return self._stub_section(role, "Раздел процессов доступен только администратору.")
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Согласования, нарушения и замещения.",
                buttons=admin_workflow_buttons(),
            ),
            active_flow=None,
        )

    def _admin_reports_menu(self, role: str) -> MaxWebhookResponse:
        if role != Role.ADMIN.value:
            return self._stub_section(role, "Раздел отчетов доступен только администратору.")
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Сводка и отчеты.",
                buttons=admin_reports_buttons(),
            ),
            active_flow=None,
        )

    def _whoami(self, role: str, user_id: str, chat_id: str) -> MaxWebhookResponse:
        local_record = self.employee_directory_repository.get_by_user_id(user_id)
        activity_record = self.user_bot_activity_repository.get_by_user_id(user_id)
        sheet_record = None if local_record is not None else self.google_directory_service.get_by_user_id(user_id)
        directory_record = local_record or sheet_record
        if directory_record is not None:
            sheet_role = GoogleSheetsDirectoryService.normalize_role_value(directory_record.role or "-")
            source_label = "локальном справочнике" if local_record is not None else "Google Sheets"
            sheet_status = (
                "Найдено в {source_label}.\n"
                "ФИО: {name}\n"
                "Подразделение: {department}\n"
                "Кабинет: {office}\n"
                "Роль в таблице: {sheet_role}\n"
                "Активен: {active}\n"
                "Руководитель: {manager}"
            ).format(
                source_label=source_label,
                name=directory_record.employee_name or "-",
                department=directory_record.department_name or "-",
                office=directory_record.office or "-",
                sheet_role=display_role_name(sheet_role),
                active="Да" if directory_record.is_active else "Нет",
                manager=directory_record.manager_name or "-",
            )
            needed_id = directory_record.employee_user_id or user_id
        elif not self._google_directory_is_configured():
            sheet_status = (
                "Google Sheets в этой runtime-среде не настроен.\n"
                "Проверка листа `Сотрудники` сейчас недоступна, поэтому это не означает, что записи нет."
            )
            needed_id = user_id
        else:
            sheet_status = "В Google Sheets по этому user_id запись не найдена."
            needed_id = user_id

        help_text = (
            "Чтобы бот показал нужные разделы, в таблице `Сотрудники` у тебя должен быть тот же ID в MAX "
            "и правильная роль.\n"
            "Нужный ID для таблицы: {needed_id}"
        ).format(needed_id=needed_id)
        device_platform = self._display_device_platform(getattr(activity_record, "device_platform", ""))
        device_link = self._device_detection_url(user_id)
        device_text = f"Устройство: {device_platform}"
        if device_link:
            device_text += f"\nОпределить устройство: {device_link}"
        buttons = [
            MaxOutboundButton(title="Обновить", action=BotAction.WHOAMI),
            MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
        ]
        if role == Role.ADMIN.value:
            buttons.insert(0, MaxOutboundButton(title="Админ-панель", action=BotAction.MENU_ADMIN_PANEL))

        text = (
            "Обо мне:\n\n"
            "{device_text}\n\n"
            "Твой ID в MAX: {user_id}\n"
            "Чат: {chat_id}\n"
            "Роль в боте: {role}\n\n"
            "{sheet_status}\n\n"
            "{help_text}"
        ).format(
            user_id=user_id,
            chat_id=chat_id,
            role=display_role_name(role),
            device_text=device_text,
            sheet_status=sheet_status,
            help_text=help_text,
        )
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=buttons,
            ),
            active_flow=None,
        )

    @staticmethod
    def _display_device_platform(value: str) -> str:
        return {
            "android": "Android",
            "ios": "iOS",
            "unknown": "неизвестно",
        }.get(str(value or "").strip().lower(), "неизвестно")

    @staticmethod
    def _device_detection_url(user_id: str) -> str:
        base = get_settings().public_base_url.strip().rstrip("/")
        if base.endswith("/api/webhooks/max"):
            base = base[: -len("/api/webhooks/max")]
        if not base:
            return ""
        return f"{base}/device?user_id={user_id}"

    def _my_row(self, role: str, user_id: str) -> MaxWebhookResponse:
        sheet_record = self.google_directory_service.get_by_user_id(user_id)
        if sheet_record is None and not self._google_directory_is_configured():
            text = (
                "Google Sheets в этой runtime-среде не настроен.\n\n"
                "Я не могу проверить лист `Сотрудники`, поэтому сейчас не подтверждаю и не опровергаю твою строку."
            )
        elif sheet_record is None:
            text = (
                "Твоя строка в таблице не найдена.\n\n"
                "Проверь, что в листе `Сотрудники` у тебя указан тот же ID в MAX."
            )
        else:
            text = (
                "Моя строка:\n\n"
                "ФИО: {name}\n"
                "ID в MAX: {user_id}\n"
                "Роль: {role}\n"
                "Подразделение: {department}\n"
                "Кабинет: {office}\n"
                "Руководитель: {manager}\n"
                "Активен: {active}"
            ).format(
                name=sheet_record.employee_name or "-",
                user_id=sheet_record.employee_user_id or "-",
                role=display_role_name(sheet_record.role or "-"),
                department=sheet_record.department_name or "-",
                office=sheet_record.office or "-",
                manager=sheet_record.manager_name or "-",
                active="Да" if sheet_record.is_active else "Нет",
            )
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Обо мне", action=BotAction.WHOAMI),
                    MaxOutboundButton(title="Админ-панель", action=BotAction.MENU_ADMIN_PANEL),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _binding_check(self, role: str, user_id: str) -> MaxWebhookResponse:
        sheet_record = self.google_directory_service.get_by_user_id(user_id)
        if sheet_record is None and not self._google_directory_is_configured():
            text = (
                "Проверка связки сейчас недоступна.\n\n"
                "Google Sheets в этой runtime-среде не настроен, поэтому я не могу сверить лист `Сотрудники`.\n"
                "Твой текущий ID в MAX: {user_id}"
            ).format(user_id=user_id)
        elif sheet_record is None:
            text = (
                "Связку не нашел.\n\n"
                "Проверь, что в листе `Сотрудники` у тебя указан тот же ID в MAX.\n"
                "Сейчас у тебя: {user_id}"
            ).format(user_id=user_id)
        else:
            text = (
                "Связку нашел.\n\n"
                "Твой ID в MAX: {user_id}\n"
                "ID в таблице: {sheet_user_id}\n"
                "Роль: {role}\n"
                "ФИО: {name}\n"
                "Совпадение: {match}"
            ).format(
                user_id=user_id,
                sheet_user_id=sheet_record.employee_user_id,
                role=display_role_name(sheet_record.role or "-"),
                name=sheet_record.employee_name or "-",
                match="Да" if sheet_record.employee_user_id == user_id else "Нет",
            )
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Моя строка", action=BotAction.MENU_MY_ROW),
                    MaxOutboundButton(title="Админ-панель", action=BotAction.MENU_ADMIN_PANEL),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _google_directory_is_configured(self) -> bool:
        checker = getattr(self.google_directory_service, "is_configured", None)
        if callable(checker):
            try:
                return bool(checker())
            except Exception:
                return False
        return False

    def _handle_attachments(self, role: str, user_id: str, attachments: list, message_id: str = "") -> MaxWebhookResponse | None:
        file_attachments = [attachment for attachment in attachments if self._is_supported_file_attachment(attachment)]
        if not file_attachments:
            return None

        results = self.max_file_import_service.import_attachments(
            file_attachments,
            created_by_user_id=user_id,
            message_id=message_id,
        )
        if not results:
            return None

        text = "Спасибо, файл получен. Обрабатываю выгрузку СКУД.\n\nВот что получилось:\n\n" + "\n\n".join(
            result.message for result in results
        )
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="История импортов", action=BotAction.MENU_IMPORT_HISTORY),
                    MaxOutboundButton(title="Назад", action=self._skud_back_action(role)),
                ],
            ),
            active_flow=None,
        )

    @staticmethod
    def _is_supported_file_attachment(attachment: object) -> bool:
        attachment_type = getattr(attachment, "type", "")
        if attachment_type in {"file", "document"}:
            return True
        payload = getattr(attachment, "payload", None)
        if payload and (getattr(payload, "url", "") or getattr(payload, "token", "")):
            return True
        return False

    def _employee_cases(self, role: str, user_id: str) -> MaxWebhookResponse:
        rows = self._list_employee_cases_for_user(user_id)
        if not rows:
            text = (
                "У тебя пока нет зарегистрированных случаев.\n\n"
                "Если справочник сотрудников еще не загружен, сначала импортируй его через раздел `Сотрудники`."
            )
            buttons = [
                MaxOutboundButton(title="Назад", action=BotAction.EMPLOYEE_REASONS),
                MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
            ]
        else:
            lines = []
            buttons: List[MaxOutboundButton] = []
            for case in rows[:8]:
                lines.append(
                    "#{id} | {date} | {kind} | статус: {status}".format(
                        id=case.id,
                        date=case.event_date,
                        kind=self._case_kind_label(case.case_type, getattr(case, "source", "")),
                        status=self._status_label(case.status),
                    )
                )
                buttons.append(
                    MaxOutboundButton(
                        title="Открыть #{0}".format(case.id),
                        action="{0}{1}".format(BotAction.EMPLOYEE_CASE_OPEN_PREFIX, case.id),
                    )
                )
            buttons.append(MaxOutboundButton(title="Назад", action=BotAction.EMPLOYEE_REASONS))
            buttons.append(MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU))
            text = "Твои случаи:\n\n{0}".format("\n".join(lines))

        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(text=text, buttons=buttons),
            active_flow=None,
        )

    def _employee_pending_reason_cases(self, role: str, user_id: str) -> MaxWebhookResponse:
        rows = self._list_pending_reason_cases_for_user(user_id)
        if not rows:
            return MaxWebhookResponse(
                ok=True,
                role=role,
                menu=get_menu_for_role(role),
                outbound=MaxOutboundMessage(
                    text="У тебя нет случаев, которые нужно объяснить.",
                    buttons=[
                        MaxOutboundButton(title="Назад", action=BotAction.EMPLOYEE_REASONS),
                        MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                    ],
                ),
                active_flow=None,
            )

        lines = []
        buttons: List[MaxOutboundButton] = []
        for case in rows[:8]:
            lines.append(
                "#{id} | {date} | {kind}".format(
                    id=case.id,
                    date=case.event_date,
                    kind=self._case_kind_label(case.case_type, getattr(case, "source", "")),
                )
            )
            buttons.append(
                    MaxOutboundButton(
                    title="Объяснить по #{0}".format(case.id),
                    action="{0}{1}".format(BotAction.EMPLOYEE_CASE_OPEN_PREFIX, case.id),
                )
            )
        buttons.append(MaxOutboundButton(title="Назад", action=BotAction.EMPLOYEE_REASONS))
        buttons.append(MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU))
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Выбери случай, который нужно объяснить:\n\n{0}".format("\n".join(lines)),
                buttons=buttons,
            ),
            active_flow=None,
        )

    def _employee_case_statuses(self, role: str, user_id: str) -> MaxWebhookResponse:
        rows = self._list_employee_cases_for_user(user_id)
        if not rows:
            return MaxWebhookResponse(
                ok=True,
                role=role,
                menu=get_menu_for_role(role),
                outbound=MaxOutboundMessage(
                    text="У тебя пока нет случаев со статусами.",
                    buttons=[
                        MaxOutboundButton(title="Назад", action=BotAction.EMPLOYEE_PERSONAL),
                        MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                    ],
                ),
                active_flow=None,
            )

        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Статусы твоих случаев:\n\n" + "\n".join(
                    "#{id} | {date} | {status}".format(
                        id=case.id,
                        date=case.event_date,
                        status=self._status_label(case.status),
                    )
                    for case in rows[:8]
                ),
                buttons=[
                    MaxOutboundButton(title="Назад", action=BotAction.EMPLOYEE_PERSONAL),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _stub_section(self, role: str, text: str) -> MaxWebhookResponse:
        buttons = [MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU)]
        if role in WORKFLOW_ROLES:
            buttons.append(MaxOutboundButton(title="Замещения", action=BotAction.MENU_SUBSTITUTIONS))
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=buttons,
            ),
            active_flow=None,
        )

    def _approvals_list(self, role: str, user_id: str, action: str, prefix_text: str = "") -> MaxWebhookResponse:
        if action == BotAction.APPROVALS_HISTORY:
            rows = self._manager_approval_rows(
                user_id,
                statuses=[ApprovalStatus.APPROVED.value, ApprovalStatus.REJECTED.value],
            )
            heading = "История согласований"
        elif action == BotAction.APPROVALS_OVERDUE:
            rows = self._manager_overdue_approval_rows(user_id)
            heading = "Просроченные согласования"
        else:
            rows = self._manager_approval_rows(user_id, statuses=[ApprovalStatus.PENDING.value])
            heading = "Согласования в ожидании"

        if not rows:
            text = prefix_text + "У тебя нет согласований в этом разделе."
            buttons = [MaxOutboundButton(title="Назад", action=BotAction.MENU_APPROVALS)]
        else:
            lines = []
            buttons = []
            for approval, case in rows[:8]:
                status_label = self._approval_status_label(approval.status)
                lines.append(
                    "#{approval_id} | {employee} | {date} | {kind} | {status}".format(
                        approval_id=approval.id,
                        employee=case.employee_name,
                        date=case.event_date,
                        kind=self._case_kind_label(case.case_type, getattr(case, "source", "")),
                        status=status_label,
                    )
                )
                if approval.status == ApprovalStatus.PENDING.value:
                    buttons.append(
                        MaxOutboundButton(
                            title="Открыть #{0}".format(approval.id),
                            action="{0}{1}".format(BotAction.APPROVAL_OPEN_PREFIX, approval.id),
                        )
                    )
            buttons.append(MaxOutboundButton(title="Назад", action=BotAction.MENU_APPROVALS))
            text = prefix_text + "{heading}:\n\n{lines}".format(heading=heading, lines="\n".join(lines))

        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(text=text, buttons=buttons),
            active_flow=None,
        )

    def _approval_card(self, role: str, user_id: str, approval_id: int) -> MaxWebhookResponse:
        rows = self._manager_approval_rows(user_id, statuses=[ApprovalStatus.PENDING.value], limit=500)
        target = None
        for approval, case in rows:
            if approval.id == approval_id:
                target = (approval, case)
                break

        if target is None:
            return self._stub_section(role, "Согласование #{0} не найдено.".format(approval_id))

        approval, case = target
        text = (
            "Согласование #{approval_id}\n\n"
            "Сотрудник: {employee}\n"
            "Подразделение: {department}\n"
            "Дата: {date}\n"
            "Тип: {kind}\n"
            "План: {planned}\n"
            "Факт: {actual}\n"
            "Опоздание: {delay} мин\n"
            "Причина сотрудника: {reason}"
        ).format(
            approval_id=approval.id,
            employee=case.employee_name,
            department=case.department_name,
            date=case.event_date,
            kind=self._case_kind_label(case.case_type, getattr(case, "source", "")),
            planned=case.planned_start,
            actual=case.actual_start,
            delay=case.delay_minutes,
            reason=case.employee_reason or "-",
        )
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(text=text, buttons=approval_card_buttons(approval.id)),
            active_flow=None,
        )

    def _employee_case_card(self, role: str, user_id: str, case_id: int) -> MaxWebhookResponse:
        case = self.case_repository.get(case_id)
        if case is None or case.employee_user_id != user_id:
            return self._stub_section(role, "Случай #{0} не найден.".format(case_id))

        require_reason = case.status == AttendanceCaseStatus.AWAITING_EMPLOYEE_REASON.value
        period_from, period_to = self._extract_period_bounds(case.employee_reason or "")
        allow_return_early = self._is_return_early_case_allowed(case)
        period_line = ""
        if period_from and period_to:
            period_line = "Период: {date_from} - {date_to}\n".format(
                date_from=period_from,
                date_to=period_to,
            )
        text = (
            "Случай #{id}\n\n"
            "Дата: {date}\n"
            "{period}"
            "Тип: {kind}\n"
            "Подразделение: {department}\n"
            "План: {planned}\n"
            "Факт: {actual}\n"
            "Опоздание: {delay} мин\n"
            "Статус: {status}\n"
            "Причина: {reason}"
        ).format(
            id=case.id,
            date=case.event_date,
            period=period_line,
            kind=self._case_kind_label(case.case_type, getattr(case, "source", "")),
            department=case.department_name,
            planned=case.planned_start,
            actual=case.actual_start,
            delay=case.delay_minutes,
            status=self._status_label(case.status),
            reason=case.employee_reason or "-",
        )
        if require_reason:
            buttons = [
                MaxOutboundButton(title="Объяснить", action=f"{BotAction.EMPLOYEE_REASON_START_PREFIX}{case.id}", emoji="✍️", row=0),
                MaxOutboundButton(title="Назад", action=BotAction.MENU_MY_LATES, emoji="↩️", row=1),
                MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=1),
            ]
        else:
            buttons = employee_case_buttons(case.id, require_reason=False, allow_return_early=allow_return_early)
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(text=text, buttons=buttons),
            active_flow=None,
        )

    def _start_approval_rejection_flow(self, role: str, user_id: str, approval_id: int) -> MaxWebhookResponse:
        target = self._pending_approval_for_manager(user_id, approval_id)
        if target is None:
            return self._stub_section(role, "Согласование #{0} не найдено.".format(approval_id))

        approval, case = target
        if not self._approval_rejection_requires_comment(case):
            approval = self.approval_repository.update_status(approval_id, ApprovalStatus.REJECTED.value)
            self._notify_employee_about_approval_decision(approval, approved=False)
            return self._approvals_list(
                role,
                user_id,
                BotAction.APPROVALS_IN_PROGRESS,
                prefix_text="Согласование #{0} отклонено.\n\n".format(approval_id),
            )

        dialog_state_store.set(
            user_id,
            UserDialogState(
                flow=DialogFlow.APPROVAL_REJECTION.value,
                step="enter_reason",
                data={"approval_id": str(approval.id)},
            ),
        )
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=(
                    "Причина отказа по согласованию #{approval_id}\n\n"
                    "Сотрудник: {employee}\n"
                    "Тип: {kind}\n"
                    "Дата: {date}\n\n"
                    "Напиши причину отказа."
                ).format(
                    approval_id=approval.id,
                    employee=case.employee_name,
                    kind=self._case_kind_label(case.case_type, getattr(case, "source", "")),
                    date=case.event_date or "-",
                ),
                buttons=[
                    MaxOutboundButton(title="Назад", action="{0}{1}".format(BotAction.APPROVAL_OPEN_PREFIX, approval.id), emoji="↩️", row=0),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                ],
            ),
            active_flow=DialogFlow.APPROVAL_REJECTION.value,
        )

    def _handle_approval_rejection_flow(
        self,
        role: str,
        user_id: str,
        user_text: str,
        action: str,
        state: UserDialogState,
    ) -> MaxWebhookResponse:
        approval_id = int(state.data.get("approval_id") or 0)
        if action == BotAction.BACK or action.startswith(BotAction.APPROVAL_OPEN_PREFIX):
            dialog_state_store.reset(user_id)
            return self._approval_card(role, user_id, approval_id)
        if action == BotAction.MAIN_MENU:
            dialog_state_store.reset(user_id)
            return self._menu_response(role, "Главное меню готово.", user_id)

        comment = str(user_text or "").strip()
        if not comment:
            return MaxWebhookResponse(
                ok=True,
                role=role,
                menu=get_menu_for_role(role),
                outbound=MaxOutboundMessage(
                    text="Напиши причину отказа текстом.",
                    buttons=[
                        MaxOutboundButton(title="Назад", action="{0}{1}".format(BotAction.APPROVAL_OPEN_PREFIX, approval_id), emoji="↩️", row=0),
                        MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                    ],
                ),
                active_flow=DialogFlow.APPROVAL_REJECTION.value,
            )

        approval = self.approval_repository.update_status(approval_id, ApprovalStatus.REJECTED.value, comment=comment)
        dialog_state_store.reset(user_id)
        self._notify_employee_about_approval_decision(approval, approved=False)
        return self._approvals_list(
            role,
            user_id,
            BotAction.APPROVALS_IN_PROGRESS,
            prefix_text="Согласование #{0} отклонено.\nПричина: {1}\n\n".format(approval_id, comment),
        )

    def _pending_approval_for_manager(self, user_id: str, approval_id: int):
        rows = self._manager_approval_rows(user_id, statuses=[ApprovalStatus.PENDING.value], limit=500)
        for approval, case in rows:
            if approval.id == approval_id:
                return approval, case
        return None

    @staticmethod
    def _approval_rejection_requires_comment(case) -> bool:
        source = str(getattr(case, "source", "") or "").strip()
        return source == "forgot_chip" or source.startswith("late_notice")

    def _start_absence_period_edit_flow(self, role: str, user_id: str, case_id: int) -> MaxWebhookResponse:
        case = self.case_repository.get(case_id)
        if case is None or case.employee_user_id != user_id:
            return self._stub_section(role, "Случай #{0} не найден.".format(case_id))
        if not self._is_return_early_case_allowed(case):
            return self._stub_section(role, "Для случая #{0} нельзя изменить дату окончания.".format(case_id))

        date_from, date_to = self._extract_period_bounds(case.employee_reason or "")
        reason_label = self._extract_period_reason_label(case.employee_reason or "")
        dialog_state_store.set(
            user_id,
            UserDialogState(
                flow=DialogFlow.ABSENCE_PERIOD_EDIT.value,
                step="enter_date_to",
                data={
                    "case_id": str(case.id),
                    "date_from": date_from,
                    "date_to": date_to,
                    "reason_label": reason_label,
                },
            ),
        )
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=(
                    "Случай #{case_id}\n\n"
                    "Причина: {reason}\n"
                    "Текущий период: {date_from} - {date_to}\n\n"
                    "Напиши новую дату окончания в формате `ГГГГ-ММ-ДД` или `ДД.ММ.ГГГГ`."
                ).format(
                    case_id=case.id,
                    reason=reason_label or "Отсутствие",
                    date_from=date_from,
                    date_to=date_to,
                ),
                buttons=[
                    MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                ],
            ),
            active_flow=DialogFlow.ABSENCE_PERIOD_EDIT.value,
        )

    def _start_forgot_chip_flow(self, role: str, user_id: str) -> MaxWebhookResponse:
        employee_record = self._resolve_directory_record_by_user_id(user_id, refresh_on_miss=True)
        if employee_record is None:
            return self._stub_section(role, "Не нашел твою строку в справочнике сотрудников. Сначала проверь привязку ID.")

        candidates = self._build_late_notice_manager_options(employee_record, role)
        if not candidates:
            if role == Role.MANAGER.value:
                return self._stub_section(role, "Не удалось подобрать топ-руководителя для согласования.")
            return self._stub_section(role, "Не удалось подобрать руководителя для согласования.")

        buttons = [
            MaxOutboundButton(
                title=name,
                action=f"{BotAction.FORGOT_CHIP_MANAGER_PREFIX}{manager_user_id}",
                emoji="👔",
                row=index // 2,
            )
            for index, (manager_user_id, name) in enumerate(candidates[:6])
        ]
        buttons.append(MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=len(buttons) // 2 + 1))
        buttons.append(MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=len(buttons) // 2 + 1))

        dialog_state_store.set(
            user_id,
            UserDialogState(
                flow=DialogFlow.FORGOT_CHIP.value,
                step="choose_manager",
                data={
                    "employee_name": employee_record.employee_name,
                    "department_name": employee_record.department_name,
                    "schedule_name": getattr(employee_record, "schedule_name", ""),
                    "schedule_id": getattr(employee_record, "schedule_id", ""),
                    "manager_options": {manager_user_id: name for manager_user_id, name in candidates[:6]},
                },
            ),
        )
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Забыл карточку СКУД.\n\nВыбери руководителя, которому уйдет согласование.",
                buttons=buttons,
            ),
            active_flow=DialogFlow.FORGOT_CHIP.value,
        )

    def _start_running_late_flow(self, role: str, user_id: str) -> MaxWebhookResponse:
        employee_record = self._resolve_directory_record_by_user_id(user_id, refresh_on_miss=True)
        if employee_record is None:
            return self._stub_section(role, "Не нашел твою строку в справочнике сотрудников. Сначала проверь привязку ID.")

        candidates = self._build_late_notice_manager_options(employee_record, role)
        if not candidates:
            if role == Role.MANAGER.value:
                return self._stub_section(role, "Не удалось подобрать топ-руководителя для согласования.")
            return self._stub_section(role, "Не удалось подобрать руководителя для согласования.")

        buttons = [
            MaxOutboundButton(
                title=name,
                action=f"{BotAction.LATE_NOTICE_MANAGER_PREFIX}{manager_user_id}",
                emoji="👔",
                row=index // 2,
            )
            for index, (manager_user_id, name) in enumerate(candidates[:6])
        ]
        buttons.append(MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=len(buttons) // 2 + 1))
        buttons.append(MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=len(buttons) // 2 + 1))

        dialog_state_store.set(
            user_id,
            UserDialogState(
                flow=DialogFlow.RUNNING_LATE.value,
                step="choose_manager",
                data={
                    "employee_name": employee_record.employee_name,
                    "department_name": employee_record.department_name,
                    "schedule_name": getattr(employee_record, "schedule_name", ""),
                    "schedule_id": getattr(employee_record, "schedule_id", ""),
                    "manager_options": {manager_user_id: name for manager_user_id, name in candidates[:6]},
                },
            ),
        )
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Опаздываю.\n\nВыбери руководителя, которому уйдет уведомление.",
                buttons=buttons,
            ),
            active_flow=DialogFlow.RUNNING_LATE.value,
        )

    def _start_attendance_reason_flow(self, role: str, user_id: str, case_id: int) -> MaxWebhookResponse:
        case = self.case_repository.get(case_id)
        if case is None or case.employee_user_id != user_id:
            return self._stub_section(role, "Случай #{0} не найден.".format(case_id))

        candidates = self._build_manager_options(
            department_name=case.department_name,
            current_manager_user_id=case.manager_user_id,
            current_manager_name=case.manager_name,
        )
        if not candidates:
            if case.manager_user_id:
                candidates = [(case.manager_user_id, case.manager_name or "Руководитель")]
            else:
                return self._stub_section(role, "Не удалось подобрать руководителя для согласования.")

        buttons = [
            MaxOutboundButton(
                title=name,
                action=f"{BotAction.EMPLOYEE_MANAGER_PREFIX}{case.id}:{manager_user_id}",
                emoji="👔",
                row=index // 2,
            )
            for index, (manager_user_id, name) in enumerate(candidates[:6])
        ]
        buttons.append(MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=len(buttons) // 2 + 1))
        buttons.append(MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=len(buttons) // 2 + 1))

        dialog_state_store.set(
            user_id,
            UserDialogState(
                flow=DialogFlow.ATTENDANCE_REASON.value,
                step="choose_manager",
                data={"case_id": str(case.id)},
            ),
        )
        text = (
            "Выбери руководителя для согласования по случаю #{id}.\n\n"
            "Если нужного человека нет в списке, будет использован текущий руководитель из таблицы."
        ).format(id=case.id)
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(text=text, buttons=buttons),
            active_flow=DialogFlow.ATTENDANCE_REASON.value,
        )

    def _resolve_reason_manager_options(self, case) -> List[Tuple[str, str]]:
        return self._build_manager_options(
            department_name=case.department_name,
            current_manager_user_id=case.manager_user_id,
            current_manager_name=case.manager_name,
        )

    def _build_manager_options(
        self,
        *,
        department_name: str,
        current_manager_user_id: str = "",
        current_manager_name: str = "",
    ) -> List[Tuple[str, str]]:
        options: List[Tuple[str, str]] = []
        seen: set[str] = set()
        directory_rows = self._resolve_directory_rows_recent(limit=300)

        def add_option(manager_user_id: str, manager_name: str) -> None:
            manager_user_id = str(manager_user_id or "").strip()
            manager_name = str(manager_name or "").strip() or "Руководитель"
            if not manager_user_id or manager_user_id in seen:
                return
            seen.add(manager_user_id)
            options.append((manager_user_id, manager_name))

        resolved_manager_user_id = str(current_manager_user_id or "").strip()
        resolved_manager_name = str(current_manager_name or "").strip()
        if resolved_manager_name:
            named_manager_row = None
            for row in directory_rows:
                if not row.is_active:
                    continue
                if (row.employee_name or "").strip() == resolved_manager_name and row.employee_user_id:
                    named_manager_row = row
                    break
            if named_manager_row is not None:
                named_manager_user_id = str(named_manager_row.employee_user_id or "").strip()
                if not resolved_manager_user_id:
                    resolved_manager_user_id = named_manager_user_id
                elif named_manager_user_id != resolved_manager_user_id:
                    resolved_manager_user_id = named_manager_user_id
                resolved_manager_name = (named_manager_row.employee_name or resolved_manager_name).strip()

        active_replacements = self._active_manager_replacements(
            department_name=department_name,
            manager_user_id=resolved_manager_user_id,
            manager_name=resolved_manager_name,
        )
        substituted_manager_ids = {
            manager_user_id for manager_user_id, _, _ in active_replacements if manager_user_id
        }
        for _, replacement_user_id, replacement_name in active_replacements:
            add_option(replacement_user_id, replacement_name)

        if resolved_manager_user_id and resolved_manager_user_id not in substituted_manager_ids:
            add_option(resolved_manager_user_id, resolved_manager_name or "Руководитель")

        department_key = str(department_name or "").strip().lower()
        for row in directory_rows:
            if not row.is_active:
                continue
            if str(getattr(row, "employee_user_id", "") or "").strip() in substituted_manager_ids:
                continue
            if row.role not in {Role.MANAGER.value, Role.ADMIN.value, Role.TOP_MANAGER.value}:
                continue
            row_department = str(getattr(row, "department_name", "") or "").strip().lower()
            if department_key and row_department and row_department != department_key:
                continue
            add_option(row.employee_user_id, row.employee_name or row.manager_name or "Руководитель")

        return options

    def _active_manager_replacements(
        self,
        *,
        department_name: str,
        manager_user_id: str = "",
        manager_name: str = "",
    ) -> List[Tuple[str, str, str]]:
        department_key = str(department_name or "").strip()
        manager_user_id = str(manager_user_id or "").strip()
        manager_name = str(manager_name or "").strip()
        if not manager_user_id and not manager_name:
            return []
        today = datetime.now().date().isoformat()
        replacements: List[Tuple[str, str, str]] = []
        seen: set[str] = set()
        for draft in self.substitution_repository.list_approved_overlapping(today, today):
            departments = self.substitution_repository.departments_for_draft(draft)
            target_user_id = str(getattr(draft, "target_user_id", "") or "").strip()
            target_name = str(getattr(draft, "target_manager", "") or "").strip()
            manager_matches = bool(
                (manager_user_id and target_user_id and target_user_id == manager_user_id)
                or (manager_name and target_name and target_name == manager_name)
            )
            department_matches = bool(department_key and department_key in departments)
            if not manager_matches and not department_matches:
                continue
            replacement_user_id = str(getattr(draft, "replacement_user_id", "") or "").strip()
            if not replacement_user_id or replacement_user_id in seen:
                continue
            replacement_name = str(getattr(draft, "replacement_user", "") or "").strip()
            if not replacement_name:
                replacement_record = self._resolve_directory_record_by_user_id(replacement_user_id)
                replacement_name = (
                    replacement_record.employee_name
                    if replacement_record is not None and getattr(replacement_record, "employee_name", "")
                    else "Замещающий руководитель"
                )
            seen.add(replacement_user_id)
            replacements.append((target_user_id, replacement_user_id, replacement_name))
        return replacements

    def _build_late_notice_manager_options(self, employee_record, role: str) -> List[Tuple[str, str]]:
        manager_user_id = str(getattr(employee_record, "manager_user_id", "") or "").strip()
        manager_name = str(getattr(employee_record, "manager_name", "") or "").strip()
        if manager_name:
            manager_record = self._resolve_directory_record_by_employee_name(manager_name)
            if manager_record is not None:
                manager_user_id = str(getattr(manager_record, "employee_user_id", "") or manager_user_id).strip()
                manager_name = str(getattr(manager_record, "employee_name", "") or manager_name).strip()
        if not manager_user_id:
            return []
        replacements = self._active_manager_replacements(
            department_name=getattr(employee_record, "department_name", ""),
            manager_user_id=manager_user_id,
            manager_name=manager_name,
        )
        if replacements:
            return [(replacement_user_id, replacement_name) for _, replacement_user_id, replacement_name in replacements]
        return [(manager_user_id, manager_name or "Руководитель")]

    def _build_top_manager_options(
        self,
        *,
        current_manager_user_id: str = "",
        current_manager_name: str = "",
    ) -> List[Tuple[str, str]]:
        options: List[Tuple[str, str]] = []
        seen: set[str] = set()
        directory_rows = self._resolve_directory_rows_recent(limit=300)

        def add_option(manager_user_id: str, manager_name: str) -> None:
            manager_user_id = str(manager_user_id or "").strip()
            manager_name = str(manager_name or "").strip() or "Главный руководитель"
            if not manager_user_id or manager_user_id in seen:
                return
            seen.add(manager_user_id)
            options.append((manager_user_id, manager_name))

        resolved_manager_user_id = str(current_manager_user_id or "").strip()
        resolved_manager_name = str(current_manager_name or "").strip()
        if resolved_manager_user_id:
            manager_record = self._resolve_directory_record_by_user_id(resolved_manager_user_id)
            if manager_record is not None and getattr(manager_record, "is_active", True):
                if getattr(manager_record, "role", "") == Role.TOP_MANAGER.value:
                    add_option(manager_record.employee_user_id, manager_record.employee_name or resolved_manager_name)
                else:
                    top_user_id = str(getattr(manager_record, "manager_user_id", "") or "").strip()
                    top_name = str(getattr(manager_record, "manager_name", "") or "").strip()
                    top_record = self._resolve_directory_record_by_user_id(top_user_id) if top_user_id else None
                    if top_record is not None and getattr(top_record, "is_active", True) and getattr(top_record, "role", "") == Role.TOP_MANAGER.value:
                        add_option(top_record.employee_user_id, top_record.employee_name or top_name)

        if not options and resolved_manager_name:
            manager_record = next(
                (
                    row
                    for row in directory_rows
                    if getattr(row, "is_active", True)
                    and str(getattr(row, "employee_name", "") or "").strip() == resolved_manager_name
                    and getattr(row, "role", "") == Role.TOP_MANAGER.value
                ),
                None,
            )
            if manager_record is not None:
                add_option(manager_record.employee_user_id, manager_record.employee_name or resolved_manager_name)

        for row in directory_rows:
            if not getattr(row, "is_active", True):
                continue
            if getattr(row, "role", "") != Role.TOP_MANAGER.value:
                continue
            add_option(row.employee_user_id, row.employee_name or row.manager_name or "Главный руководитель")

        return options

    @staticmethod
    def _running_late_back_action(role: str) -> str:
        if role == Role.EMPLOYEE.value:
            return BotAction.EMPLOYEE_REASONS
        if role == Role.ADMIN.value:
            return BotAction.ADMIN_PERSONAL
        return BotAction.MAIN_MENU

    def _running_late_back_response(self, role: str, user_id: str = "") -> MaxWebhookResponse:
        if role == Role.EMPLOYEE.value:
            return self._employee_reason_menu(role)
        if role == Role.ADMIN.value:
            return self._admin_personal_menu(role)
        return self._menu_response(role, "Главное меню готово.", user_id)

    def _handle_attendance_reason_flow(
        self,
        role: str,
        user_id: str,
        user_text: str,
        action: str,
        state,
    ) -> MaxWebhookResponse:
        case_id = int(state.data.get("case_id", "0") or 0)
        case = self.case_repository.get(case_id)
        if case is None or case.employee_user_id != user_id:
            dialog_state_store.reset(user_id)
            return self._stub_section(role, "Случай #{0} не найден.".format(case_id))

        if state.step == "choose_manager" and action.startswith(BotAction.EMPLOYEE_MANAGER_PREFIX):
            _, remainder = action.split(BotAction.EMPLOYEE_MANAGER_PREFIX, 1)
            case_part, manager_user_id = remainder.split(":", 1)
            if int(case_part) != case_id:
                return self._stub_section(role, "Случай #{0} не найден.".format(case_id))
            manager_record = self._resolve_directory_record_by_user_id(manager_user_id)
            manager_name = ""
            if manager_record is not None:
                manager_name = manager_record.employee_name or manager_record.manager_name
            if not manager_name:
                manager_name = "Руководитель"

            self.case_repository.update_manager(case_id, manager_user_id, manager_name)
            state.step = "choose_reason"
            state.data["manager_user_id"] = manager_user_id
            state.data["manager_name"] = manager_name
            dialog_state_store.set(user_id, state)
            buttons = attendance_reason_buttons(case_id)
            text = (
                "Руководитель выбран: {manager}\n\n"
                "Теперь выбери причину по случаю #{case_id}."
            ).format(manager=manager_name, case_id=case_id)
            return MaxWebhookResponse(
                ok=True,
                role=role,
                menu=get_menu_for_role(role),
                outbound=MaxOutboundMessage(text=text, buttons=buttons),
                active_flow=DialogFlow.ATTENDANCE_REASON.value,
            )

        if action == BotAction.BACK or user_text == "Назад":
            if state.step == "choose_manager":
                dialog_state_store.reset(user_id)
                return self._employee_pending_reason_cases(role, user_id)
            if state.step == "choose_reason":
                return self._start_attendance_reason_flow(role, user_id, case_id)

        if state.step == "choose_reason" and action.startswith(BotAction.EMPLOYEE_REASON_PREFIX):
            _, remainder = action.split(BotAction.EMPLOYEE_REASON_PREFIX, 1)
            case_part, reason_code = remainder.split(":", 1)
            if int(case_part) != case_id:
                return self._stub_section(role, "Случай #{0} не найден.".format(case_id))
            response = self._employee_submit_reason(
                role,
                user_id,
                action,
                manager_override=state.data.get("manager_user_id"),
                manager_name_override=state.data.get("manager_name"),
            )
            dialog_state_store.reset(user_id)
            return response

        manager_name = state.data.get("manager_name", "руководителя")
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Сначала выбери руководителя, затем причину. Текущий выбор: {0}".format(manager_name),
                buttons=[
                    MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                ],
            ),
            active_flow=DialogFlow.ATTENDANCE_REASON.value,
        )

    def _handle_forgot_chip_flow(
        self,
        role: str,
        user_id: str,
        user_text: str,
        action: str,
        state,
    ) -> MaxWebhookResponse:
        if action == BotAction.BACK or user_text == "Назад":
            if state.step == "choose_manager":
                dialog_state_store.reset(user_id)
                return self._running_late_back_response(role, user_id)
            return self._start_forgot_chip_flow(role, user_id)

        if state.step == "choose_manager" and action.startswith(BotAction.FORGOT_CHIP_MANAGER_PREFIX):
            manager_user_id = action.split(BotAction.FORGOT_CHIP_MANAGER_PREFIX, 1)[1]
            manager_name = state.data.get("manager_options", {}).get(manager_user_id)
            if not manager_name:
                manager_record = self._resolve_directory_record_by_user_id(manager_user_id)
                manager_name = manager_record.employee_name if manager_record is not None else "Руководитель"
            state.step = "enter_time"
            state.data["manager_user_id"] = manager_user_id
            state.data["manager_name"] = manager_name
            dialog_state_store.set(user_id, state)
            return MaxWebhookResponse(
                ok=True,
                role=role,
                menu=get_menu_for_role(role),
                outbound=MaxOutboundMessage(
                    text="Руководитель выбран: {manager}\n\nНапиши время прихода в формате ЧЧ:ММ, например `08:27`.".format(
                        manager=manager_name
                    ),
                    buttons=[
                        MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                        MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                    ],
                ),
                active_flow=DialogFlow.FORGOT_CHIP.value,
            )

        if state.step == "enter_time":
            arrival_time = self._normalize_hhmm(user_text)
            if arrival_time is None:
                return MaxWebhookResponse(
                    ok=True,
                    role=role,
                    menu=get_menu_for_role(role),
                    outbound=MaxOutboundMessage(
                        text="Нужен формат времени ЧЧ:ММ. Пример: `08:27`.",
                        buttons=[
                            MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                            MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                        ],
                    ),
                    active_flow=DialogFlow.FORGOT_CHIP.value,
                )

            event_day = datetime.now().date()
            planned_start = self.google_schedule_service.resolve_planned_start(
                schedule_id=state.data.get("schedule_id", ""),
                schedule_name=state.data.get("schedule_name", ""),
                event_date=event_day,
                fallback="08:30",
            )
            delay_minutes = self._late_delay_minutes(planned_start, arrival_time)
            reason_text = "Забыл карточку СКУД. Указанное время прихода: {time}".format(time=arrival_time)
            case_id = self.case_repository.create_case(
                employee_user_id=user_id,
                employee_name=state.data.get("employee_name", ""),
                department_name=state.data.get("department_name", ""),
                manager_user_id=state.data.get("manager_user_id", ""),
                manager_name=state.data.get("manager_name", "Руководитель"),
                case_type=AttendanceCaseType.LATE.value,
                status=AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value,
                event_date=event_day.isoformat(),
                planned_start=planned_start,
                actual_start=arrival_time,
                delay_minutes=delay_minutes,
                employee_reason=reason_text,
                source="forgot_chip",
            )
            approval_id = self.approval_repository.create_if_missing(
                case_id=case_id,
                manager_user_id=state.data.get("manager_user_id", ""),
                manager_name=state.data.get("manager_name", "Руководитель"),
                status=ApprovalStatus.PENDING.value,
            )
            case = self.case_repository.get(case_id)
            if case is not None:
                self._notify_manager_about_reason(case, reason_text, approval_id, background=True)
            dialog_state_store.reset(user_id)
            return MaxWebhookResponse(
                ok=True,
                role=role,
                menu=get_menu_for_role(role),
                outbound=MaxOutboundMessage(
                    text=(
                        "Заявка `Забыл карточку СКУД` отправлена на согласование.\n\n"
                        "Дата: {date}\n"
                        "Время прихода: {time}\n"
                        "Руководитель: {manager}"
                    ).format(
                        date=event_day.isoformat(),
                        time=arrival_time,
                        manager=state.data.get("manager_name", "Руководитель"),
                    ),
                    buttons=[
                        MaxOutboundButton(title="Назад", action=self._running_late_back_action(role)),
                        MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                    ],
                ),
                active_flow=None,
            )

        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Сначала выбери руководителя, потом укажи время прихода.",
                buttons=[
                    MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                ],
            ),
            active_flow=DialogFlow.FORGOT_CHIP.value,
        )

    def _handle_running_late_flow(
        self,
        role: str,
        user_id: str,
        user_text: str,
        action: str,
        state,
    ) -> MaxWebhookResponse:
        if action == BotAction.BACK or user_text == "Назад":
            if state.step == "choose_manager":
                dialog_state_store.reset(user_id)
                return self._running_late_back_response(role, user_id)
            if state.step == "choose_date":
                return self._start_running_late_flow(role, user_id)
            if state.step == "choose_reason":
                state.step = "choose_date"
                dialog_state_store.set(user_id, state)
                return MaxWebhookResponse(
                    ok=True,
                    role=role,
                    menu=get_menu_for_role(role),
                    outbound=MaxOutboundMessage(
                        text="Выбери дату опоздания.",
                        buttons=running_late_date_buttons(),
                    ),
                    active_flow=DialogFlow.RUNNING_LATE.value,
                )
            if state.step == "enter_date_to":
                state.step = "enter_date_from"
                dialog_state_store.set(user_id, state)
                return MaxWebhookResponse(
                    ok=True,
                    role=role,
                    menu=get_menu_for_role(role),
                    outbound=MaxOutboundMessage(
                        text=(
                            "Буду отсутствовать.\n\n"
                            "Напиши дату начала в формате `ГГГГ-ММ-ДД` или `ДД.ММ.ГГГГ`."
                        ),
                        buttons=[
                            MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                            MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                        ],
                    ),
                    active_flow=DialogFlow.RUNNING_LATE.value,
                )
            if state.step == "enter_absence_reason":
                state.step = "enter_date_to"
                dialog_state_store.set(user_id, state)
                date_from = state.data.get("notice_date_from", "")
                return MaxWebhookResponse(
                    ok=True,
                    role=role,
                    menu=get_menu_for_role(role),
                    outbound=MaxOutboundMessage(
                        text=(
                            "Дата начала: {date_from}\n\n"
                            "Теперь напиши дату окончания в формате `ГГГГ-ММ-ДД` или `ДД.ММ.ГГГГ`."
                        ).format(date_from=date_from),
                        buttons=[
                            MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                            MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                        ],
                    ),
                    active_flow=DialogFlow.RUNNING_LATE.value,
                )
            if state.step == "enter_date_from":
                state.step = "choose_date"
                dialog_state_store.set(user_id, state)
                return MaxWebhookResponse(
                    ok=True,
                    role=role,
                    menu=get_menu_for_role(role),
                    outbound=MaxOutboundMessage(
                        text="Выбери дату опоздания.",
                        buttons=running_late_date_buttons(),
                    ),
                    active_flow=DialogFlow.RUNNING_LATE.value,
                )
            if state.step == "enter_other_reason":
                state.step = "choose_reason"
                dialog_state_store.set(user_id, state)
                manager_name = state.data.get("manager_name", "руководитель")
                return MaxWebhookResponse(
                    ok=True,
                    role=role,
                    menu=get_menu_for_role(role),
                    outbound=MaxOutboundMessage(
                        text="Руководитель выбран: {manager}\n\nУкажи причину опоздания.".format(manager=manager_name),
                        buttons=running_late_reason_buttons(),
                    ),
                    active_flow=DialogFlow.RUNNING_LATE.value,
                )
            if state.step in {"enter_time", "enter_date"}:
                state.step = "choose_reason"
                dialog_state_store.set(user_id, state)
                manager_name = state.data.get("manager_name", "руководитель")
                return MaxWebhookResponse(
                    ok=True,
                    role=role,
                    menu=get_menu_for_role(role),
                    outbound=MaxOutboundMessage(
                        text="Руководитель выбран: {manager}\n\nУкажи причину опоздания.".format(manager=manager_name),
                        buttons=running_late_reason_buttons(),
                    ),
                    active_flow=DialogFlow.RUNNING_LATE.value,
                )

        if state.step == "choose_manager" and action.startswith(BotAction.LATE_NOTICE_MANAGER_PREFIX):
            manager_user_id = action.split(BotAction.LATE_NOTICE_MANAGER_PREFIX, 1)[1]
            manager_name = state.data.get("manager_options", {}).get(manager_user_id)
            if not manager_name:
                manager_record = self._resolve_directory_record_by_user_id(manager_user_id)
                manager_name = manager_record.employee_name if manager_record is not None else "Руководитель"
            state.step = "choose_date"
            state.data["manager_user_id"] = manager_user_id
            state.data["manager_name"] = manager_name
            dialog_state_store.set(user_id, state)
            return MaxWebhookResponse(
                ok=True,
                role=role,
                menu=get_menu_for_role(role),
                outbound=MaxOutboundMessage(
                    text="Руководитель выбран: {manager}\n\nВыбери дату опоздания.".format(manager=manager_name),
                    buttons=running_late_date_buttons(),
                ),
                active_flow=DialogFlow.RUNNING_LATE.value,
            )

        if state.step == "choose_date" and action.startswith(BotAction.LATE_NOTICE_DATE_PREFIX):
            date_code = action.split(BotAction.LATE_NOTICE_DATE_PREFIX, 1)[1]
            today = datetime.now().date()
            if date_code == "today":
                event_day = today
                date_label = "Сегодня"
            elif date_code == "tomorrow":
                event_day = today + timedelta(days=1)
                date_label = "Завтра"
            else:
                return MaxWebhookResponse(
                    ok=True,
                    role=role,
                    menu=get_menu_for_role(role),
                    outbound=MaxOutboundMessage(
                        text="Выбери дату кнопкой: Сегодня или Завтра.",
                        buttons=running_late_date_buttons(),
                    ),
                    active_flow=DialogFlow.RUNNING_LATE.value,
                )
            state.step = "choose_reason"
            state.data["notice_event_date"] = event_day.isoformat()
            dialog_state_store.set(user_id, state)
            return MaxWebhookResponse(
                ok=True,
                role=role,
                menu=get_menu_for_role(role),
                outbound=MaxOutboundMessage(
                    text="{date_label}: {date}\n\nУкажи причину опоздания.".format(
                        date_label=date_label,
                        date=event_day.isoformat(),
                    ),
                    buttons=running_late_reason_buttons(),
                ),
                active_flow=DialogFlow.RUNNING_LATE.value,
            )

        if state.step == "choose_reason" and action.startswith(BotAction.LATE_NOTICE_REASON_PREFIX):
            reason_code = action.split(BotAction.LATE_NOTICE_REASON_PREFIX, 1)[1]
            if reason_code != AttendanceReasonCode.OTHER.value:
                return MaxWebhookResponse(
                    ok=True,
                    role=role,
                    menu=get_menu_for_role(role),
                    outbound=MaxOutboundMessage(
                        text="Для опоздания теперь причина вводится вручную. Нажми `Указать причину`.",
                        buttons=running_late_reason_buttons(),
                    ),
                    active_flow=DialogFlow.RUNNING_LATE.value,
                )
            reason_label = LATE_NOTICE_REASON_LABELS.get(reason_code, reason_code)
            state.data["notice_reason_code"] = reason_code
            state.data["notice_reason_label"] = reason_label
            state.step = "enter_other_reason"
            dialog_state_store.set(user_id, state)
            return MaxWebhookResponse(
                ok=True,
                role=role,
                menu=get_menu_for_role(role),
                outbound=MaxOutboundMessage(
                    text="Напиши причину опоздания.",
                    buttons=[
                        MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                        MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                    ],
                ),
                active_flow=DialogFlow.RUNNING_LATE.value,
            )

        if state.step == "enter_other_reason":
            reason_text = str(user_text or "").strip()
            if not reason_text:
                return MaxWebhookResponse(
                    ok=True,
                    role=role,
                    menu=get_menu_for_role(role),
                    outbound=MaxOutboundMessage(
                        text="Напиши причину опоздания текстом.",
                        buttons=[
                            MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                            MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                        ],
                    ),
                    active_flow=DialogFlow.RUNNING_LATE.value,
                )
            state.data["notice_reason_label"] = reason_text
            state.step = "enter_time"
            dialog_state_store.set(user_id, state)
            return MaxWebhookResponse(
                ok=True,
                role=role,
                menu=get_menu_for_role(role),
                outbound=MaxOutboundMessage(
                    text=(
                        "Причина: {reason}\n\n"
                        "Напиши, со скольки опаздываешь, в формате ЧЧ:ММ."
                    ).format(reason=reason_text),
                    buttons=[
                        MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                        MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                    ],
                ),
                active_flow=DialogFlow.RUNNING_LATE.value,
            )

        if state.step == "enter_time":
            late_from_time = self._normalize_hhmm(user_text)
            if late_from_time is None:
                return MaxWebhookResponse(
                    ok=True,
                    role=role,
                    menu=get_menu_for_role(role),
                    outbound=MaxOutboundMessage(
                        text="Нужен формат времени ЧЧ:ММ. Пример: `08:47`.",
                        buttons=[
                            MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                            MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                        ],
                    ),
                    active_flow=DialogFlow.RUNNING_LATE.value,
                )
            reason_label = state.data.get("notice_reason_label", "")
            event_day_raw = state.data.get("notice_event_date") or datetime.now().date().isoformat()
            event_day = datetime.strptime(event_day_raw, "%Y-%m-%d").date()
            planned_start = self.google_schedule_service.resolve_planned_start(
                schedule_id=state.data.get("schedule_id", ""),
                schedule_name=state.data.get("schedule_name", ""),
                event_date=event_day,
                fallback="08:30",
            )
            reason_text = "Опаздываю с {time}. Причина: {reason}".format(
                time=late_from_time,
                reason=reason_label,
            )
            case_id = self.case_repository.create_case(
                employee_user_id=user_id,
                employee_name=state.data.get("employee_name", ""),
                department_name=state.data.get("department_name", ""),
                manager_user_id=state.data.get("manager_user_id", ""),
                manager_name=state.data.get("manager_name", "Руководитель"),
                case_type=AttendanceCaseType.LATE.value,
                status=AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value,
                event_date=event_day.isoformat(),
                planned_start=planned_start,
                actual_start=late_from_time,
                delay_minutes=0,
                employee_reason=reason_text,
                source="late_notice",
            )
            approval_id = self.approval_repository.create_if_missing(
                case_id=case_id,
                manager_user_id=state.data.get("manager_user_id", ""),
                manager_name=state.data.get("manager_name", "Руководитель"),
                status=ApprovalStatus.PENDING.value,
            )
            case = self.case_repository.get(case_id)
            if case is not None:
                self._notify_manager_about_late_notice(case, late_from_time, reason_label, approval_id, background=True)
            dialog_state_store.reset(user_id)
            return MaxWebhookResponse(
                ok=True,
                role=role,
                menu=get_menu_for_role(role),
                outbound=MaxOutboundMessage(
                    text=(
                        "Предупреждение об опоздании отправлено на согласование.\n\n"
                        "Дата: {date}\n"
                        "Опаздываю с: {time}\n"
                        "Причина: {reason}\n"
                        "Руководитель: {manager}"
                    ).format(
                        date=event_day.isoformat(),
                        time=late_from_time,
                        reason=reason_label,
                        manager=state.data.get("manager_name", "Руководитель"),
                    ),
                    buttons=[
                        MaxOutboundButton(title="Назад", action=self._running_late_back_action(role)),
                        MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                    ],
                ),
                active_flow=None,
            )

        if state.step == "enter_absence_reason":
            absence_reason = str(user_text or "").strip()
            if not absence_reason:
                return MaxWebhookResponse(
                    ok=True,
                    role=role,
                    menu=get_menu_for_role(role),
                    outbound=MaxOutboundMessage(
                        text="Напиши причину отсутствия.",
                        buttons=[
                            MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                            MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                        ],
                    ),
                    active_flow=DialogFlow.RUNNING_LATE.value,
                )

            date_from = state.data.get("notice_date_from", "")
            date_to = state.data.get("notice_date_to", "")
            event_day = datetime.strptime(date_from, "%Y-%m-%d").date()
            planned_start = self.google_schedule_service.resolve_planned_start(
                schedule_id=state.data.get("schedule_id", ""),
                schedule_name=state.data.get("schedule_name", ""),
                event_date=event_day,
                fallback="08:30",
            )
            reason_text = self._build_period_reason_text(absence_reason, date_from, date_to)
            case_id = self.case_repository.create_case(
                employee_user_id=user_id,
                employee_name=state.data.get("employee_name", ""),
                department_name=state.data.get("department_name", ""),
                manager_user_id=state.data.get("manager_user_id", ""),
                manager_name=state.data.get("manager_name", "Руководитель"),
                case_type=AttendanceCaseType.ABSENT.value,
                status=AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value,
                event_date=date_from,
                planned_start=planned_start,
                actual_start="",
                delay_minutes=0,
                employee_reason=reason_text,
                source="attendance_notice",
            )
            approval_id = self.approval_repository.create_if_missing(
                case_id=case_id,
                manager_user_id=state.data.get("manager_user_id", ""),
                manager_name=state.data.get("manager_name", "Руководитель"),
                status=ApprovalStatus.PENDING.value,
            )
            case = self.case_repository.get(case_id)
            if case is not None:
                self._notify_manager_about_absence_notice(case, reason_text, approval_id)
            dialog_state_store.reset(user_id)
            return MaxWebhookResponse(
                ok=True,
                role=role,
                menu=get_menu_for_role(role),
                outbound=MaxOutboundMessage(
                    text=(
                        "Заявка отправлена на согласование.\n\n"
                        "Период: {date_from} - {date_to}\n"
                        "Причина: {reason}\n"
                        "Руководитель: {manager}"
                    ).format(
                        date_from=date_from,
                        date_to=date_to,
                        reason=absence_reason,
                        manager=state.data.get("manager_name", "Руководитель"),
                    ),
                    buttons=[
                        MaxOutboundButton(title="Назад", action=self._running_late_back_action(role)),
                        MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                    ],
                ),
                active_flow=None,
            )

        if state.step == "enter_date":
            notice_date = self._normalize_date(user_text)
            if notice_date is None:
                return MaxWebhookResponse(
                    ok=True,
                    role=role,
                    menu=get_menu_for_role(role),
                    outbound=MaxOutboundMessage(
                        text="Нужна дата в формате `ГГГГ-ММ-ДД` или `ДД.ММ.ГГГГ`.",
                        buttons=[
                            MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                            MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                        ],
                    ),
                    active_flow=DialogFlow.RUNNING_LATE.value,
                )

            reason_label = state.data.get("notice_reason_label", "")
            event_day = datetime.strptime(notice_date, "%Y-%m-%d").date()
            planned_start = self.google_schedule_service.resolve_planned_start(
                schedule_id=state.data.get("schedule_id", ""),
                schedule_name=state.data.get("schedule_name", ""),
                event_date=event_day,
                fallback="08:30",
            )
            reason_text = "{reason}. Дата: {date}".format(reason=reason_label, date=notice_date)
            case_id = self.case_repository.create_case(
                employee_user_id=user_id,
                employee_name=state.data.get("employee_name", ""),
                department_name=state.data.get("department_name", ""),
                manager_user_id=state.data.get("manager_user_id", ""),
                manager_name=state.data.get("manager_name", "Руководитель"),
                case_type=AttendanceCaseType.ABSENT.value,
                status=AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value,
                event_date=notice_date,
                planned_start=planned_start,
                actual_start="",
                delay_minutes=0,
                employee_reason=reason_text,
                source="attendance_notice",
            )
            approval_id = self.approval_repository.create_if_missing(
                case_id=case_id,
                manager_user_id=state.data.get("manager_user_id", ""),
                manager_name=state.data.get("manager_name", "Руководитель"),
                status=ApprovalStatus.PENDING.value,
            )
            case = self.case_repository.get(case_id)
            if case is not None:
                self._notify_manager_about_absence_notice(case, reason_text, approval_id)
            dialog_state_store.reset(user_id)
            return MaxWebhookResponse(
                ok=True,
                role=role,
                menu=get_menu_for_role(role),
                outbound=MaxOutboundMessage(
                    text=(
                        "Заявка отправлена на согласование.\n\n"
                        "Дата: {date}\n"
                        "Причина: {reason}\n"
                        "Руководитель: {manager}"
                    ).format(
                        date=notice_date,
                        reason=reason_label,
                        manager=state.data.get("manager_name", "Руководитель"),
                    ),
                    buttons=[
                        MaxOutboundButton(title="Назад", action=self._running_late_back_action(role)),
                        MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                    ],
                ),
                active_flow=None,
            )

        if state.step == "enter_date_from":
            date_from = self._normalize_date(user_text)
            if date_from is None:
                return MaxWebhookResponse(
                    ok=True,
                    role=role,
                    menu=get_menu_for_role(role),
                    outbound=MaxOutboundMessage(
                        text="Нужна дата начала в формате `ГГГГ-ММ-ДД` или `ДД.ММ.ГГГГ`.",
                        buttons=[
                            MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                            MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                        ],
                    ),
                    active_flow=DialogFlow.RUNNING_LATE.value,
                )

            state.step = "enter_date_to"
            state.data["notice_date_from"] = date_from
            dialog_state_store.set(user_id, state)
            return MaxWebhookResponse(
                ok=True,
                role=role,
                menu=get_menu_for_role(role),
                outbound=MaxOutboundMessage(
                    text=(
                        "Дата начала: {date_from}\n\n"
                        "Теперь напиши дату окончания в формате `ГГГГ-ММ-ДД` или `ДД.ММ.ГГГГ`."
                    ).format(date_from=date_from),
                    buttons=[
                        MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                        MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                    ],
                ),
                active_flow=DialogFlow.RUNNING_LATE.value,
            )

        if state.step == "enter_date_to":
            date_to = self._normalize_date(user_text)
            if date_to is None:
                return MaxWebhookResponse(
                    ok=True,
                    role=role,
                    menu=get_menu_for_role(role),
                    outbound=MaxOutboundMessage(
                        text="Нужна дата окончания в формате `ГГГГ-ММ-ДД` или `ДД.ММ.ГГГГ`.",
                        buttons=[
                            MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                            MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                        ],
                    ),
                    active_flow=DialogFlow.RUNNING_LATE.value,
                )

            date_from = state.data.get("notice_date_from", "")
            if date_from and date_to < date_from:
                return MaxWebhookResponse(
                    ok=True,
                    role=role,
                    menu=get_menu_for_role(role),
                    outbound=MaxOutboundMessage(
                        text="Дата окончания не может быть раньше даты начала.",
                        buttons=[
                            MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                            MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                        ],
                    ),
                    active_flow=DialogFlow.RUNNING_LATE.value,
                )

            state.step = "enter_absence_reason"
            state.data["notice_date_to"] = date_to
            dialog_state_store.set(user_id, state)
            return MaxWebhookResponse(
                ok=True,
                role=role,
                menu=get_menu_for_role(role),
                outbound=MaxOutboundMessage(
                    text=(
                        "Период: {date_from} - {date_to}\n\n"
                        "Напиши причину отсутствия."
                    ).format(
                        date_from=date_from,
                        date_to=date_to,
                    ),
                    buttons=[
                        MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                        MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                    ],
                ),
                active_flow=DialogFlow.RUNNING_LATE.value,
            )

        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Сначала выбери руководителя, затем причину, а потом укажи время или дату.",
                buttons=[
                    MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                ],
            ),
            active_flow=DialogFlow.RUNNING_LATE.value,
        )

    def _handle_absence_period_edit_flow(
        self,
        role: str,
        user_id: str,
        user_text: str,
        action: str,
        state,
    ) -> MaxWebhookResponse:
        case_id = int(state.data.get("case_id", "0") or 0)
        case = self.case_repository.get(case_id)
        if case is None or case.employee_user_id != user_id:
            dialog_state_store.reset(user_id)
            return self._stub_section(role, "Случай #{0} не найден.".format(case_id))

        if action == BotAction.BACK or user_text == "Назад":
            dialog_state_store.reset(user_id)
            return self._employee_case_card(role, user_id, case_id)

        if state.step != "enter_date_to":
            return self._employee_case_card(role, user_id, case_id)

        new_date_to = self._normalize_date(user_text)
        if new_date_to is None:
            return MaxWebhookResponse(
                ok=True,
                role=role,
                menu=get_menu_for_role(role),
                outbound=MaxOutboundMessage(
                    text="Нужна дата окончания в формате `ГГГГ-ММ-ДД` или `ДД.ММ.ГГГГ`.",
                    buttons=[
                        MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                        MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                    ],
                ),
                active_flow=DialogFlow.ABSENCE_PERIOD_EDIT.value,
            )

        date_from = state.data.get("date_from", "")
        current_date_to = state.data.get("date_to", "")
        reason_label = state.data.get("reason_label", "") or self._extract_period_reason_label(case.employee_reason or "")
        if date_from and new_date_to < date_from:
            return MaxWebhookResponse(
                ok=True,
                role=role,
                menu=get_menu_for_role(role),
                outbound=MaxOutboundMessage(
                    text="Дата окончания не может быть раньше даты начала.",
                    buttons=[
                        MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                        MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                    ],
                ),
                active_flow=DialogFlow.ABSENCE_PERIOD_EDIT.value,
            )
        if current_date_to and new_date_to > current_date_to:
            return MaxWebhookResponse(
                ok=True,
                role=role,
                menu=get_menu_for_role(role),
                outbound=MaxOutboundMessage(
                    text="Новая дата окончания должна быть не позже текущей даты окончания.",
                    buttons=[
                        MaxOutboundButton(title="Назад", action=BotAction.BACK, emoji="↩️", row=0),
                        MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                    ],
                ),
                active_flow=DialogFlow.ABSENCE_PERIOD_EDIT.value,
            )

        updated_reason_text = self._build_period_reason_text(reason_label, date_from, new_date_to)
        updated_case = self.case_repository.update_reason_and_status(
            case_id,
            updated_reason_text,
            AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value,
        )
        approval_id = self.approval_repository.create_if_missing(
            case_id=case_id,
            manager_user_id=case.manager_user_id,
            manager_name=case.manager_name or "Руководитель",
            status=ApprovalStatus.PENDING.value,
        )
        if updated_case is not None:
            self._notify_manager_about_absence_period_update(
                updated_case,
                previous_date_to=current_date_to,
                new_date_to=new_date_to,
                approval_id=approval_id,
            )

        dialog_state_store.reset(user_id)
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=(
                    "Дата окончания обновлена.\n\n"
                    "Период: {date_from} - {date_to}\n"
                    "Руководитель получит обновление на согласование."
                ).format(
                    date_from=date_from,
                    date_to=new_date_to,
                ),
                buttons=[
                    MaxOutboundButton(title="Назад", action=f"{BotAction.EMPLOYEE_CASE_OPEN_PREFIX}{case_id}", emoji="↩️", row=0),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                ],
            ),
            active_flow=None,
        )

    def _employee_submit_reason(
        self,
        role: str,
        user_id: str,
        action: str,
        manager_override: Optional[str] = None,
        manager_name_override: Optional[str] = None,
    ) -> MaxWebhookResponse:
        _, remainder = action.split(BotAction.EMPLOYEE_REASON_PREFIX, 1)
        case_part, reason_code = remainder.split(":", 1)
        case_id = int(case_part)
        case = self.case_repository.get(case_id)
        if case is None or case.employee_user_id != user_id:
            return self._stub_section(role, "Случай #{0} не найден.".format(case_id))

        reason_label = ATTENDANCE_REASON_LABELS.get(reason_code, reason_code)
        manager_user_id = manager_override or case.manager_user_id
        manager_name = manager_name_override or case.manager_name or "Руководитель"
        if manager_user_id:
            update_manager = getattr(self.case_repository, "update_manager", None)
            if callable(update_manager):
                update_manager(case_id, manager_user_id, manager_name)
        self.case_repository.update_reason_and_status(
            case_id=case_id,
            employee_reason=reason_label,
            status=AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value,
        )
        approval_id = None
        if manager_user_id:
            approval_id = self.approval_repository.create_if_missing(
                case_id=case_id,
                manager_user_id=manager_user_id,
                manager_name=manager_name,
                status=ApprovalStatus.PENDING.value,
            )
            refreshed = self.case_repository.get(case_id)
            self._notify_manager_about_reason(refreshed or case, reason_label, approval_id)

        refreshed = self.case_repository.get(case_id)
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Причина по случаю #{id} сохранена: {reason}.\nСтатус: {status}".format(
                    id=case_id,
                    reason=reason_label,
                    status=self._status_label(
                        refreshed.status if refreshed else AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value
                    ),
                ),
                buttons=[
                    MaxOutboundButton(title="Назад", action=BotAction.EMPLOYEE_REASONS),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _notify_manager_about_reason(self, case, reason_label: str, approval_id: int | None, *, background: bool = False) -> None:
        if not self.max_client.is_configured() or not case.manager_user_id:
            return

        approval_text = (
            "Новая причина по случаю #{case_id}\n\n"
            "Сотрудник: {employee}\n"
            "Подразделение: {department}\n"
            "Дата: {date}\n"
            "Тип: {kind}\n"
            "Опоздание: {delay} мин\n"
            "Причина: {reason}"
        ).format(
            case_id=case.id,
            employee=case.employee_name,
            department=case.department_name,
            date=case.event_date,
            kind=self._case_kind_label(case.case_type, getattr(case, "source", "")),
            delay=case.delay_minutes,
            reason=reason_label,
        )
        buttons = approval_notification_buttons(approval_id) if approval_id else [MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0)]
        self._send_max_message(
            background=background,
            user_id=case.manager_user_id,
            text=approval_text,
            buttons=buttons,
        )

    def _send_max_message(self, *, background: bool = False, **kwargs) -> None:
        if background:
            thread = threading.Thread(target=self._send_max_message, kwargs=kwargs, daemon=True)
            thread.start()
            return
        try:
            self.max_client.send_message(**kwargs)
        except Exception:
            return

    def _notify_manager_about_late_notice(
        self,
        case,
        late_from_time: str,
        reason_label: str,
        approval_id: int | None,
        *,
        background: bool = False,
    ) -> None:
        if not self.max_client.is_configured() or not case.manager_user_id:
            return

        notice_text = (
            "Сотрудник предупредил об опоздании\n\n"
            "Сотрудник: {employee}\n"
            "Подразделение: {department}\n"
            "Дата: {date}\n"
            "Тип: {kind}\n"
            "Опаздывает с: {late_from}\n"
            "Причина: {reason}"
        ).format(
            employee=case.employee_name,
            department=case.department_name,
            date=case.event_date,
            kind=self._case_kind_label(case.case_type, getattr(case, "source", "")),
            late_from=late_from_time,
            reason=reason_label,
        )
        buttons = approval_notification_buttons(approval_id) if approval_id else [MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0)]
        self._send_max_message(
            background=background,
            user_id=case.manager_user_id,
            text=notice_text,
            buttons=buttons,
        )

    def _notify_manager_about_absence_notice(
        self,
        case,
        reason_text: str,
        approval_id: int | None,
    ) -> None:
        if not self.max_client.is_configured() or not case.manager_user_id:
            return

        notice_text = (
            "Сотрудник заранее сообщил об отсутствии\n\n"
            "Сотрудник: {employee}\n"
            "Подразделение: {department}\n"
            "Дата: {date}\n"
            "Тип: {kind}\n"
            "Причина: {reason}"
        ).format(
            employee=case.employee_name,
            department=case.department_name,
            date=case.event_date,
            kind=self._case_kind_label(case.case_type, getattr(case, "source", "")),
            reason=reason_text,
        )
        buttons = approval_notification_buttons(approval_id) if approval_id else [MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0)]
        try:
            self.max_client.send_message(
                user_id=case.manager_user_id,
                text=notice_text,
                buttons=buttons,
            )
        except Exception:
            return

    def _notify_manager_about_absence_period_update(
        self,
        case,
        previous_date_to: str,
        new_date_to: str,
        approval_id: int | None,
    ) -> None:
        if not self.max_client.is_configured() or not case.manager_user_id:
            return

        date_from, _ = self._extract_period_bounds(getattr(case, "employee_reason", ""))
        notice_text = (
            "Сотрудник обновил период отсутствия\n\n"
            "Сотрудник: {employee}\n"
            "Подразделение: {department}\n"
            "Тип: {kind}\n"
            "Было до: {previous_date_to}\n"
            "Теперь до: {new_date_to}\n"
            "Период: {date_from} - {new_date_to}\n"
            "Причина: {reason}"
        ).format(
            employee=case.employee_name,
            department=case.department_name,
            kind=self._case_kind_label(case.case_type, getattr(case, "source", "")),
            previous_date_to=previous_date_to or "-",
            new_date_to=new_date_to,
            date_from=date_from or case.event_date,
            reason=case.employee_reason or "-",
        )
        buttons = approval_notification_buttons(approval_id) if approval_id else [MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0)]
        try:
            self.max_client.send_message(
                user_id=case.manager_user_id,
                text=notice_text,
                buttons=buttons,
            )
        except Exception:
            return

    def _notify_replacement_about_substitution(
        self,
        *,
        draft_id: int,
        replacement_user_id: str,
        target_manager: str,
        replacement_user: str,
        date_from: str,
        date_to: str,
        reason: str,
        departments: str,
    ) -> None:
        if not self.max_client.is_configured() or not replacement_user_id:
            return
        departments_label = self._substitution_departments_label(departments)
        text = (
            "Тебя выбрали замещающим сотрудником\n\n"
            "Кого замещаешь: {target}\n"
            "Ты: {replacement}\n"
            "Причина: {reason}\n"
            "Период: {date_from} -> {date_to}\n"
            "Курируемые отделы: {departments}\n\n"
            "Открой запрос и подтверди или отклони его."
        ).format(
            target=target_manager or "-",
            replacement=replacement_user or "-",
            reason=reason or "-",
            date_from=date_from or "-",
            date_to=date_to or "-",
            departments=departments_label,
        )
        try:
            self.max_client.send_message(
                user_id=replacement_user_id,
                text=text,
                buttons=substitution_notification_buttons(draft_id),
            )
        except Exception:
            return

    def _notify_initiator_about_substitution_decision(self, draft, *, approved: bool) -> None:
        if not self.max_client.is_configured() or not getattr(draft, "created_by_user_id", ""):
            return
        if approved:
            text = (
                "Твое замещение согласовано\n\n"
                "Замещающий: {replacement}\n"
                "Период: {date_from} -> {date_to}"
            ).format(
                replacement=draft.replacement_user or "-",
                date_from=draft.date_from or "-",
                date_to=draft.date_to or "-",
            )
        else:
            text = (
                "Твое замещение отклонено\n\n"
                "Замещающий: {replacement}\n"
                "Период: {date_from} -> {date_to}"
            ).format(
                replacement=draft.replacement_user or "-",
                date_from=draft.date_from or "-",
                date_to=draft.date_to or "-",
            )
        try:
            self.max_client.send_message(
                user_id=draft.created_by_user_id,
                text=text,
                buttons=[MaxOutboundButton(title="Мои замещения", action=BotAction.SUBSTITUTION_LIST, emoji="📋", row=0)],
            )
        except Exception:
            return

    def _notify_employee_about_approval_decision(self, approval, *, approved: bool) -> None:
        if approval is None or not self.max_client.is_configured():
            return

        case = self.case_repository.get(int(getattr(approval, "case_id", 0) or 0))
        if case is None:
            return

        employee_user_id = str(getattr(case, "employee_user_id", "") or "").strip()
        if not employee_user_id:
            directory_record = self._resolve_directory_record_by_employee_name(getattr(case, "employee_name", ""))
            employee_user_id = str(getattr(directory_record, "employee_user_id", "") or "").strip()
        if not employee_user_id:
            return

        decision = "согласована" if approved else "отклонена"
        approver_label = "Кто согласовал" if approved else "Кто отклонил"
        comment = str(getattr(approval, "comment", "") or "").strip()
        text = (
            "Твоя заявка {decision}\n\n"
            "Случай: #{case_id}\n"
            "Тип: {kind}\n"
            "Дата: {date}\n"
            "{approver_label}: {approver}"
        ).format(
            decision=decision,
            case_id=case.id,
            kind=self._case_kind_label(case.case_type, getattr(case, "source", "")),
            date=case.event_date or "-",
            approver_label=approver_label,
            approver=getattr(approval, "manager_name", "") or case.manager_name or "Руководитель",
        )
        if not approved and comment:
            text += "\nПричина отказа: {0}".format(comment)
        try:
            self._send_proactive_user_message(
                user_id=employee_user_id,
                text=text,
                buttons=[
                    MaxOutboundButton(title="Мои статусы", action=BotAction.MENU_MY_STATUSES, emoji="📎", row=0),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
                ],
            )
        except Exception:
            self.logger.warning(
                "Failed to notify employee about approval decision approval_id=%s case_id=%s employee_user_id=%s approved=%s",
                getattr(approval, "id", ""),
                getattr(approval, "case_id", ""),
                employee_user_id,
                approved,
                exc_info=True,
            )
            return

    def _send_proactive_user_message(
        self,
        *,
        user_id: str,
        text: str,
        buttons: List[MaxOutboundButton],
    ) -> None:
        last_error: Exception | None = None
        try:
            self.max_client.send_message(user_id=user_id, text=text, buttons=buttons)
            return
        except Exception as exc:
            last_error = exc
            self.logger.warning(
                "Failed to send proactive MAX message by user_id=%s; trying chat_id fallback",
                user_id,
                exc_info=True,
            )

        chat_id = ""
        getter = getattr(self.bot_message_cursor_store, "get_chat_id_for_user", None)
        if callable(getter):
            chat_id = str(getter(user_id) or "").strip()
        if chat_id:
            try:
                self.max_client.send_message(chat_id=chat_id, text=text, buttons=buttons)
                return
            except Exception as exc:
                last_error = exc
                self.logger.warning(
                    "Failed to send proactive MAX message by chat_id=%s for user_id=%s",
                    chat_id,
                    user_id,
                    exc_info=True,
                )
        if last_error is not None:
            raise last_error

    def _parse_id(self, action: str, prefix: str) -> int:
        try:
            return int(action.replace(prefix, "", 1))
        except ValueError:
            return 0

    def _substitution_list(self, role: str, user_id: str) -> MaxWebhookResponse:
        rows = self.substitution_repository.list_drafts_for_user(user_id)
        if not rows:
            text = "У тебя пока нет сохраненных черновиков замещений."
            buttons = [
                MaxOutboundButton(title="На период", action=BotAction.SUBSTITUTION_CREATE, emoji="➕", row=0),
                MaxOutboundButton(title="Назад", action=BotAction.MAIN_MENU, emoji="↩️", row=0),
            ]
        else:
            preview_lines = []
            for row in rows[:5]:
                preview_lines.append(
                    "#{id}: {target} -> {replacement} | {date_from} - {date_to} | отделы: {departments} | {status}".format(
                        id=row.id,
                        target=row.target_manager,
                        replacement=row.replacement_user,
                        date_from=row.date_from,
                        date_to=row.date_to,
                        departments=self._substitution_departments_label(getattr(row, "departments_json", "[]")),
                        status=self._substitution_status_label(row.status),
                    )
                )
            text = "Мои замещения:\n\n{lines}".format(lines="\n".join(preview_lines))
            buttons = self._substitution_draft_action_buttons(rows, mode="list")

        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=buttons,
            ),
            active_flow=None,
        )

    def _cancel_substitution_draft(self, role: str, user_id: str, draft_id: int) -> MaxWebhookResponse:
        if draft_id <= 0:
            return self._stub_section(role, "Черновик не найден.")
        draft = self.substitution_repository.cancel_draft(draft_id, user_id)
        if draft is None:
            return self._stub_section(role, "Черновик не найден или недоступен.")
        rows = self.substitution_repository.list_drafts_for_user(user_id)
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Замещение #{0} снято.\n\nМои замещения:\n\n{1}".format(
                    draft_id,
                    "\n".join(
                        "#{id}: {target} -> {replacement} | {date_from} - {date_to} | {scope} | {status}".format(
                            id=row.id,
                            target=row.target_manager,
                            replacement=row.replacement_user,
                            date_from=row.date_from,
                            date_to=row.date_to,
                            scope="отделы: {0}".format(self._substitution_departments_label(getattr(row, "departments_json", "[]"))),
                            status=self._substitution_status_label(row.status),
                        )
                        for row in rows[:5]
                    )
                    or "-",
                ),
                buttons=self._substitution_draft_action_buttons(rows, mode="list"),
            ),
            active_flow=None,
        )

    def _start_substitution_extend_flow(self, role: str, user_id: str, draft_id: int) -> MaxWebhookResponse:
        result = self.substitution_flow.start_extend(user_id, draft_id)
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=result.message,
            active_flow=DialogFlow.SUBSTITUTION.value if not result.completed else None,
        )

    def _substitution_draft_action_buttons(self, rows, mode: str) -> List[MaxOutboundButton]:
        buttons: List[MaxOutboundButton] = []
        for index, row in enumerate(rows[:5]):
            if mode == "cancel":
                buttons.append(
                    MaxOutboundButton(
                        title=f"Снять #{row.id}",
                        action=f"{BotAction.SUBSTITUTION_CANCEL_PREFIX}{row.id}",
                        emoji="🗑️",
                        row=index,
                    )
                )
            elif mode == "extend":
                buttons.append(
                    MaxOutboundButton(
                        title=f"Продлить #{row.id}",
                        action=f"{BotAction.SUBSTITUTION_EXTEND_PREFIX}{row.id}",
                        emoji="🔁",
                        row=index,
                    )
                )
            else:
                buttons.append(
                    MaxOutboundButton(
                        title=f"Снять #{row.id}",
                        action=f"{BotAction.SUBSTITUTION_CANCEL_PREFIX}{row.id}",
                        emoji="🗑️",
                        row=index,
                    )
                )
                buttons.append(
                    MaxOutboundButton(
                        title=f"Продлить #{row.id}",
                        action=f"{BotAction.SUBSTITUTION_EXTEND_PREFIX}{row.id}",
                        emoji="🔁",
                        row=index,
                    )
                )

        buttons.append(MaxOutboundButton(title="На период", action=BotAction.SUBSTITUTION_CREATE, emoji="➕", row=10))
        buttons.append(MaxOutboundButton(title="Назад", action=BotAction.MAIN_MENU, emoji="↩️", row=10))
        return buttons

    @staticmethod
    def _substitution_departments_label(raw: str) -> str:
        import json

        try:
            value = json.loads(raw or "[]")
        except json.JSONDecodeError:
            return "-"
        if not isinstance(value, list) or not value:
            return "-"
        return ", ".join(str(item).strip() for item in value if str(item).strip()) or "-"

    def _send_outbound(self, inbound: MaxUpdate, outbound: MaxOutboundMessage) -> None:
        if self.async_callback_outbound and inbound.update_type == "message_callback" and inbound.callback:
            thread = threading.Thread(
                target=self._send_outbound_in_background,
                args=(inbound, outbound),
                daemon=True,
            )
            thread.start()
            self.logger.info(
                "MAX outbound queued update_type=%s action=%s",
                inbound.update_type,
                inbound.callback.payload or "",
            )
            return
        self._send_outbound_sync(inbound, outbound)

    def _send_outbound_in_background(self, inbound: MaxUpdate, outbound: MaxOutboundMessage) -> None:
        try:
            self._send_outbound_sync(inbound, outbound)
        except Exception:
            self.logger.warning(
                "MAX outbound background send failed update_type=%s action=%s",
                inbound.update_type,
                inbound.callback.payload if inbound.callback else "",
                exc_info=True,
            )

    def _send_outbound_sync(self, inbound: MaxUpdate, outbound: MaxOutboundMessage) -> None:
        if not self.max_client.is_configured():
            return

        started_at = perf_counter()
        callback_render_ms: float | None = None
        try:
            if inbound.update_type == "message_callback" and inbound.callback:
                callback_action = inbound.callback.payload or ""
                callback_started_at = perf_counter()
                marker_key = self._outgoing_marker_key(
                    inbound,
                    "callback",
                    inbound.callback.callback_id,
                    outbound,
                )
                if marker_key and not self.runtime_marker_repository.claim(marker_key, "outgoing", lease_seconds=120):
                    return
                try:
                    if callback_action == BotAction.OFFICE_SEAL_REMINDER_ACK:
                        if inbound.message and inbound.message.body.mid:
                            message_ids = [inbound.message.body.mid]
                        else:
                            message_ids = self._previous_bot_message_ids(inbound)
                        try:
                            self.max_client.answer_callback(
                                callback_id=inbound.callback.callback_id,
                                notification=outbound.text,
                            )
                        finally:
                            self._delete_message_ids(message_ids)
                            self._cursor_reset_many(self._conversation_keys(inbound))
                        if marker_key:
                            self.runtime_marker_repository.complete(marker_key, ttl_seconds=600)
                        return
                    if inbound.message and inbound.message.body.mid:
                        previous_message_ids = [
                            message_id
                            for message_id in self._previous_bot_message_ids(inbound)
                            if message_id != inbound.message.body.mid
                        ]
                        self.max_client.answer_callback(
                            callback_id=inbound.callback.callback_id,
                            notification=INVISIBLE_MESSAGE_TEXT,
                        )
                        self.max_client.edit_message(
                            inbound.message.body.mid,
                            text=outbound.text,
                            buttons=outbound.buttons,
                        )
                        self._remember_current_callback_message(inbound, outbound.text)
                        if previous_message_ids:
                            self._queue_delete_message_ids(previous_message_ids)
                    else:
                        self.max_client.answer_callback(
                            callback_id=inbound.callback.callback_id,
                            new_text=outbound.text,
                            buttons=outbound.buttons,
                        )
                    if marker_key:
                        self.runtime_marker_repository.complete(marker_key, ttl_seconds=600)
                    callback_render_ms = (perf_counter() - callback_started_at) * 1000
                    self.logger.info(
                        "MAX outbound sent update_type=%s action=%s callback_render_ms=%.1f recipient=%s total_ms=%.1f",
                        inbound.update_type,
                        callback_action,
                        callback_render_ms,
                        "callback_message",
                        (perf_counter() - started_at) * 1000,
                    )
                    return
                except Exception:
                    if marker_key:
                        self.runtime_marker_repository.release(marker_key)
                    if not inbound.chat_id:
                        raise
                    self.logger.warning(
                        "MAX callback embedded render failed, falling back to visible message chat_id=%s user_id=%s action=%s",
                        inbound.chat_id,
                        inbound.user.user_id if inbound.user else None,
                        callback_action,
                        exc_info=True,
                    )
                visible_stats = self._send_visible_outbound(inbound, outbound)
                self.logger.info(
                    "MAX outbound sent update_type=%s action=%s callback_fallback=true delete_ms=%.1f deleted_messages=%s send_ms=%.1f recipient=%s total_ms=%.1f",
                    inbound.update_type,
                    callback_action,
                    visible_stats["delete_ms"],
                    visible_stats["deleted_messages"],
                    visible_stats["send_ms"],
                    visible_stats["recipient"],
                    (perf_counter() - started_at) * 1000,
                )
                return

            if inbound.update_type in {"bot_started", "message_created"}:
                visible_stats = self._send_visible_outbound(inbound, outbound)
                self.logger.info(
                    "MAX outbound sent update_type=%s action=%s delete_ms=%.1f deleted_messages=%s send_ms=%.1f recipient=%s total_ms=%.1f",
                    inbound.update_type,
                    getattr(inbound.callback, "payload", None) if inbound.callback else getattr(getattr(inbound.message, "body", None), "text", None),
                    visible_stats["delete_ms"],
                    visible_stats["deleted_messages"],
                    visible_stats["send_ms"],
                    visible_stats["recipient"],
                    (perf_counter() - started_at) * 1000,
                )
                return
        except Exception:
            self.logger.exception(
                "Failed to send MAX outbound update_type=%s chat_id=%s user_id=%s action=%s",
                inbound.update_type,
                inbound.chat_id,
                inbound.user.user_id if inbound.user else None,
                getattr(inbound.callback, "payload", None) if inbound.callback else getattr(getattr(inbound.message, "body", None), "text", None),
            )
            return

    def _send_visible_outbound(self, inbound: MaxUpdate, outbound: MaxOutboundMessage) -> dict[str, float | int | str]:
        delete_started_at = perf_counter()
        previous_message_ids = self._previous_bot_message_ids(inbound) if self.delete_previous_message else []
        delete_ms = (perf_counter() - delete_started_at) * 1000

        recipients = self._outbound_recipients(inbound)
        last_error: Exception | None = None
        response: dict[str, object] | None = None
        recipient_used = "none"
        send_started_at = perf_counter()
        for recipient_type, recipient_value in recipients:
            marker_key = self._outgoing_marker_key(inbound, recipient_type, str(recipient_value), outbound)
            if marker_key and not self.runtime_marker_repository.claim(marker_key, "outgoing", lease_seconds=120):
                recipient_used = f"{recipient_type}:duplicate"
                response = None
                break
            try:
                if recipient_type == "chat_id":
                    response = self.max_client.send_message(
                        chat_id=recipient_value,
                        text=outbound.text,
                        buttons=outbound.buttons,
                    )
                else:
                    response = self.max_client.send_message(
                        user_id=recipient_value,
                        text=outbound.text,
                        buttons=outbound.buttons,
                    )
                recipient_used = recipient_type
                if marker_key:
                    self.runtime_marker_repository.complete(marker_key, ttl_seconds=600)
                break
            except Exception as exc:
                if marker_key:
                    self.runtime_marker_repository.release(marker_key)
                last_error = exc
                continue

        if response is None:
            if last_error is not None:
                raise last_error
            return {
                "delete_ms": round(delete_ms, 1),
                "deleted_messages": len(previous_message_ids),
                "send_ms": round((perf_counter() - send_started_at) * 1000, 1),
                "recipient": recipient_used,
            }

        self._remember_last_bot_message(inbound, response, outbound.text)
        if previous_message_ids:
            self._queue_delete_message_ids(previous_message_ids)
        return {
            "delete_ms": round(delete_ms, 1),
            "deleted_messages": len(previous_message_ids),
            "send_ms": round((perf_counter() - send_started_at) * 1000, 1),
            "recipient": recipient_used,
        }

    def _previous_bot_message_ids(self, inbound: MaxUpdate) -> list[str]:
        conversation_keys = self._conversation_keys(inbound)
        previous_by_key = self._cursor_get_many(conversation_keys)
        seen_message_ids: set[str] = set()
        message_ids: list[str] = []
        for conversation_key in conversation_keys:
            for previous_message_id in self._cursor_message_ids(previous_by_key.get(conversation_key, "")):
                if previous_message_id in seen_message_ids:
                    continue
                seen_message_ids.add(previous_message_id)
                message_ids.append(previous_message_id)
        return message_ids

    @staticmethod
    def _cursor_message_ids(value: str) -> list[str]:
        return [item.strip() for item in str(value or "").splitlines() if item.strip()]

    def _queue_delete_message_ids(self, message_ids: list[str]) -> None:
        thread = threading.Thread(target=self._delete_message_ids, args=(message_ids,), daemon=True)
        thread.start()

    def _delete_message_ids(self, message_ids: list[str]) -> int:
        deleted_messages = 0
        for message_id in message_ids:
            try:
                self.max_client.delete_message(message_id)
                deleted_messages += 1
            except Exception:
                try:
                    soft_clear = getattr(self.max_client, "soft_clear_message", None)
                    if soft_clear is None:
                        raise
                    soft_clear(message_id)
                    deleted_messages += 1
                except Exception:
                    self.logger.warning(
                        "Failed to delete previous MAX bot message mid=%s",
                        message_id,
                    )
        return deleted_messages

    def _remember_last_bot_message(self, inbound: MaxUpdate, response: dict[str, object], outbound_text: str = "") -> None:
        text = str(outbound_text or "")
        if text.startswith("Обо мне:"):
            return
        message_id = self._extract_message_id(response)
        conversation_keys = self._conversation_keys(inbound)
        if not conversation_keys:
            return

        chat_id, user_id = self._conversation_participants(inbound)
        if not message_id:
            self._cursor_reset_many(conversation_keys)
            return

        self._cursor_set_many(conversation_keys, chat_id, user_id, message_id)

    def _remember_current_callback_message(self, inbound: MaxUpdate, outbound_text: str = "") -> None:
        if str(outbound_text or "").startswith("Обо мне:"):
            return
        message_id = ""
        if inbound.message and inbound.message.body:
            message_id = str(inbound.message.body.mid or "").strip()
        if not message_id:
            return

        conversation_keys = self._conversation_keys(inbound)
        if not conversation_keys:
            return

        chat_id, user_id = self._conversation_participants(inbound)
        self._cursor_set_many(conversation_keys, chat_id, user_id, message_id)

    def _cursor_get_many(self, conversation_keys: list[str]) -> dict[str, str]:
        getter = getattr(type(self.bot_message_cursor_store), "get_many", None)
        if callable(getter):
            values = getter(self.bot_message_cursor_store, conversation_keys)
            if isinstance(values, dict):
                return {str(key): str(value) for key, value in values.items() if value}
        return {
            key: str(value)
            for key in conversation_keys
            if (value := self.bot_message_cursor_store.get(key))
        }

    def _cursor_set_many(self, conversation_keys: list[str], chat_id: str, user_id: str, message_id: str) -> None:
        setter = getattr(type(self.bot_message_cursor_store), "set_many", None)
        if callable(setter):
            setter(self.bot_message_cursor_store, conversation_keys, chat_id, user_id, message_id)
            return
        for conversation_key in conversation_keys:
            self.bot_message_cursor_store.set(
                conversation_key=conversation_key,
                chat_id=chat_id,
                user_id=user_id,
                message_id=message_id,
            )

    def _cursor_reset_many(self, conversation_keys: list[str]) -> None:
        resetter = getattr(type(self.bot_message_cursor_store), "reset_many", None)
        if callable(resetter):
            resetter(self.bot_message_cursor_store, conversation_keys)
            return
        for conversation_key in conversation_keys:
            self.bot_message_cursor_store.reset(conversation_key)

    @staticmethod
    def _extract_message_id(response: dict[str, object]) -> str:
        candidates = [
            response.get("mid"),
            response.get("message_id"),
        ]
        message = response.get("message")
        if isinstance(message, dict):
            candidates.append(message.get("mid"))
            body = message.get("body")
            if isinstance(body, dict):
                candidates.append(body.get("mid"))
        body = response.get("body")
        if isinstance(body, dict):
            candidates.append(body.get("mid"))

        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate
        return ""

    def _send_report_files(
        self,
        chat_id: str,
        user_id: str,
        title: str,
        xlsx_path: str,
        pdf_path: str,
        xlsx_download_url: str = "",
        pdf_download_url: str = "",
    ) -> None:
        if not self.max_client.is_configured():
            return
        try:
            recipients = []
            if str(chat_id).isdigit():
                recipients.append(("chat_id", int(chat_id)))
            if str(user_id).isdigit():
                recipients.append(("user_id", int(user_id)))

            any_sent = False
            for recipient_type, recipient_value in recipients:
                send_kwargs = {"text": f"{title} в Excel", "file_path": xlsx_path}
                if recipient_type == "chat_id":
                    send_kwargs["chat_id"] = recipient_value
                else:
                    send_kwargs["user_id"] = recipient_value
                try:
                    self.max_client.send_file_message(**send_kwargs)
                    any_sent = True
                except Exception:
                    self.logger.warning(
                        "Failed to send MAX xlsx report file recipient_type=%s recipient_value=%s title=%s path=%s",
                        recipient_type,
                        recipient_value,
                        title,
                        xlsx_path,
                        exc_info=True,
                    )

                send_pdf_kwargs = {"text": f"{title} в PDF", "file_path": pdf_path}
                if recipient_type == "chat_id":
                    send_pdf_kwargs["chat_id"] = recipient_value
                else:
                    send_pdf_kwargs["user_id"] = recipient_value
                try:
                    self.max_client.send_file_message(**send_pdf_kwargs)
                    any_sent = True
                except Exception:
                    self.logger.warning(
                        "Failed to send MAX pdf report file recipient_type=%s recipient_value=%s title=%s path=%s",
                        recipient_type,
                        recipient_value,
                        title,
                        pdf_path,
                        exc_info=True,
                    )

                if any_sent:
                    return
            if not any_sent:
                self.logger.error(
                    "Failed to send any MAX report files chat_id=%s user_id=%s title=%s",
                    chat_id,
                    user_id,
                    title,
                )
                links = []
                if xlsx_download_url:
                    links.append(f"Excel: {xlsx_download_url}")
                if pdf_download_url:
                    links.append(f"PDF: {pdf_download_url}")
                if links:
                    self._send_report_message(
                        chat_id,
                        user_id,
                        "{title} готов, но MAX не принял вложения.\n\nСкачать можно по ссылкам:\n{links}".format(
                            title=title,
                            links="\n".join(links),
                        ),
                    )
        except Exception:
            self.logger.exception(
                "Failed to send MAX report files chat_id=%s user_id=%s title=%s",
                chat_id,
                user_id,
                title,
            )
            return

    def _send_report_message(self, chat_id: str, user_id: str, text: str) -> None:
        if not self.max_client.is_configured():
            return
        try:
            recipients = []
            if str(chat_id).isdigit():
                recipients.append(("chat_id", int(chat_id)))
            if str(user_id).isdigit():
                recipients.append(("user_id", int(user_id)))

            for recipient_type, recipient_value in recipients:
                try:
                    if recipient_type == "chat_id":
                        self.max_client.send_message(chat_id=recipient_value, text=text, buttons=[])
                    else:
                        self.max_client.send_message(user_id=recipient_value, text=text, buttons=[])
                    return
                except Exception:
                    continue
        except Exception:
            self.logger.exception(
                "Failed to send MAX report message chat_id=%s user_id=%s text=%s",
                chat_id,
                user_id,
                text,
            )

    def _generate_and_send_manager_report(
        self,
        chat_id: str,
        user_id: str,
        role: str,
        period: str,
        date_from: str = "",
        date_to: str = "",
    ) -> None:
        try:
            artifact = self.report_service.generate_manager_report(
                user_id=user_id,
                role=role,
                period=period,
                date_from=date_from,
                date_to=date_to,
            )
            self._send_report_files(
                chat_id,
                user_id,
                artifact.title,
                artifact.file_path,
                artifact.pdf_file_path,
                getattr(artifact, "download_url", ""),
                getattr(artifact, "pdf_download_url", ""),
            )
        except Exception:
            self.logger.exception(
                "Failed to generate manager report chat_id=%s user_id=%s role=%s period=%s date_from=%s date_to=%s",
                chat_id,
                user_id,
                role,
                period,
                date_from,
                date_to,
            )
            self._send_report_message(chat_id, user_id, "Не получилось сформировать отчет. Попробуй еще раз.")

    def _generate_and_send_division_report(
        self,
        chat_id: str,
        user_id: str,
        role: str,
        period: str,
        date_from: str = "",
        date_to: str = "",
    ) -> None:
        try:
            artifact = self.report_service.generate_division_report(
                user_id=user_id,
                role=role,
                period=period,
                date_from=date_from,
                date_to=date_to,
            )
            self._send_report_files(
                chat_id,
                user_id,
                artifact.title,
                artifact.file_path,
                artifact.pdf_file_path,
                getattr(artifact, "download_url", ""),
                getattr(artifact, "pdf_download_url", ""),
            )
        except Exception:
            self.logger.exception(
                "Failed to generate division report chat_id=%s user_id=%s role=%s period=%s date_from=%s date_to=%s",
                chat_id,
                user_id,
                role,
                period,
                date_from,
                date_to,
            )
            self._send_report_message(chat_id, user_id, "Не получилось сформировать отчет по подразделениям. Попробуй еще раз.")

    def _queue_report_files(self, chat_id: str, user_id: str, title: str, xlsx_path: str, pdf_path: str) -> None:
        thread = threading.Thread(
            target=self._send_report_files,
            kwargs={
                "chat_id": chat_id,
                "user_id": user_id,
                "title": title,
                "xlsx_path": xlsx_path,
                "pdf_path": pdf_path,
            },
            daemon=True,
        )
        thread.start()

    def _queue_manager_report(
        self,
        chat_id: str,
        user_id: str,
        role: str,
        period: str,
        date_from: str = "",
        date_to: str = "",
    ) -> None:
        thread = threading.Thread(
            target=self._generate_and_send_manager_report,
            kwargs={
                "chat_id": chat_id,
                "user_id": user_id,
                "role": role,
                "period": period,
                "date_from": date_from,
                "date_to": date_to,
            },
            daemon=True,
        )
        thread.start()

    def _queue_division_report(
        self,
        chat_id: str,
        user_id: str,
        role: str,
        period: str,
        date_from: str = "",
        date_to: str = "",
    ) -> None:
        thread = threading.Thread(
            target=self._generate_and_send_division_report,
            kwargs={
                "chat_id": chat_id,
                "user_id": user_id,
                "role": role,
                "period": period,
                "date_from": date_from,
                "date_to": date_to,
            },
            daemon=True,
        )
        thread.start()

    def _status_label(self, status: str) -> str:
        labels = {
            AttendanceCaseStatus.NEW.value: "Новый",
            AttendanceCaseStatus.AWAITING_EMPLOYEE_REASON.value: "Ожидает причину сотрудника",
            AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value: "На согласовании у руководителя",
            AttendanceCaseStatus.JUSTIFIED.value: "Подтверждено уважительно",
            AttendanceCaseStatus.UNJUSTIFIED.value: "Подтверждено неуважительно",
            AttendanceCaseStatus.CLOSED.value: "Закрыт",
        }
        return labels.get(status, status)

    def _outbound_recipients(self, inbound: MaxUpdate) -> list[tuple[str, int]]:
        recipients: list[tuple[str, int]] = []
        if inbound.chat_id:
            recipients.append(("chat_id", int(inbound.chat_id)))
        recipient_chat_id = getattr(inbound.message.recipient, "chat_id", None) if inbound.message else None
        if recipient_chat_id:
            recipients.append(("chat_id", int(recipient_chat_id)))
        callback_user_id = getattr(getattr(inbound, "callback", None), "user", None)
        callback_user_id = getattr(callback_user_id, "user_id", None)
        if callback_user_id:
            recipients.append(("user_id", int(callback_user_id)))
        if inbound.user and inbound.user.user_id:
            recipients.append(("user_id", int(inbound.user.user_id)))
        if inbound.message and inbound.message.sender and inbound.message.sender.user_id:
            recipients.append(("user_id", int(inbound.message.sender.user_id)))

        unique: list[tuple[str, int]] = []
        seen = set()
        for recipient in recipients:
            if recipient in seen:
                continue
            seen.add(recipient)
            unique.append(recipient)
        return unique

    def _outgoing_marker_key(
        self,
        inbound: MaxUpdate,
        recipient_type: str,
        recipient_value: str,
        outbound: MaxOutboundMessage,
    ) -> str:
        if not recipient_type or not recipient_value:
            return ""
        buttons = [
            {
                "title": button.title,
                "action": button.action,
                "emoji": button.emoji or "",
                "row": button.row,
            }
            for button in outbound.buttons
        ]
        digest = sha256(repr((outbound.text, buttons)).encode("utf-8")).hexdigest()[:24]
        return f"out:{recipient_type}:{recipient_value}:{digest}"

    def _conversation_participants(self, inbound: MaxUpdate) -> tuple[str, str]:
        chat_id = ""
        if inbound.chat_id:
            chat_id = str(inbound.chat_id)
        elif inbound.update_type != "message_callback" and inbound.message and inbound.message.recipient and inbound.message.recipient.chat_id:
            chat_id = str(inbound.message.recipient.chat_id)

        user_id = ""
        if inbound.callback and inbound.callback.user and inbound.callback.user.user_id:
            user_id = str(inbound.callback.user.user_id)
        elif inbound.user and inbound.user.user_id:
            user_id = str(inbound.user.user_id)
        elif inbound.message and inbound.message.sender and inbound.message.sender.user_id:
            user_id = str(inbound.message.sender.user_id)

        return chat_id, user_id

    def _conversation_key(self, inbound: MaxUpdate) -> str:
        chat_id, user_id = self._conversation_participants(inbound)
        if chat_id:
            return f"chat:{chat_id}"
        if user_id:
            return f"user:{user_id}"
        return ""

    def _conversation_keys(self, inbound: MaxUpdate) -> list[str]:
        chat_id, user_id = self._conversation_participants(inbound)
        keys: list[str] = []
        if chat_id:
            keys.append(f"chat:{chat_id}")
        if user_id:
            keys.append(f"user:{user_id}")
        return keys

    def _known_chat_id_for_user(self, user_id: str) -> str:
        getter = getattr(self.bot_message_cursor_store, "get_chat_id_for_user", None)
        if getter is None:
            return ""
        try:
            chat_id = getter(str(user_id))
        except Exception:
            return ""
        return str(chat_id or "").strip()

    def _approval_status_label(self, status: str) -> str:
        labels = {
            ApprovalStatus.PENDING.value: "Ожидает",
            ApprovalStatus.APPROVED.value: "Согласовано",
            ApprovalStatus.REJECTED.value: "Отклонено",
        }
        return labels.get(status, status)

    def _substitution_status_label(self, status: str) -> str:
        labels = {
            "pending_replacement_approval": "Ожидает согласования замещающего",
            "approved": "Согласовано замещающим",
            "rejected": "Отклонено замещающим",
            "cancelled": "Снято",
            "draft": "Черновик",
        }
        return labels.get(status, status)

    @staticmethod
    def _normalize_navigation_action(value: str) -> str:
        return re.sub(r"[^0-9a-zа-я]+", "", (value or "").strip().lower())

    @classmethod
    def _is_main_menu_action(cls, action: str, user_text: str) -> bool:
        normalized_action = cls._normalize_navigation_action(action)
        normalized_text = cls._normalize_navigation_action(user_text)
        return normalized_action in {
            cls._normalize_navigation_action(BotAction.MAIN_MENU),
            cls._normalize_navigation_action(BotAction.START),
            cls._normalize_navigation_action("/start"),
            cls._normalize_navigation_action("Старт"),
            cls._normalize_navigation_action("Начать"),
            cls._normalize_navigation_action("Главное меню"),
            cls._normalize_navigation_action("menu_main"),
            cls._normalize_navigation_action("main_menu"),
            cls._normalize_navigation_action("главноеменю"),
        } or normalized_text in {
            cls._normalize_navigation_action(BotAction.START),
            cls._normalize_navigation_action("/start"),
            cls._normalize_navigation_action("Старт"),
            cls._normalize_navigation_action("Начать"),
            cls._normalize_navigation_action("Главное меню"),
            cls._normalize_navigation_action("menu_main"),
            cls._normalize_navigation_action("main_menu"),
            cls._normalize_navigation_action("главноеменю"),
        }
