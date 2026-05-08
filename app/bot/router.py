from __future__ import annotations

import logging
import threading
import re
from typing import List, Optional, Tuple

from app.bot.actions import BotAction
from app.bot.buttons import (
    admin_personal_buttons,
    admin_reports_buttons,
    admin_settings_buttons,
    admin_skud_buttons,
    admin_structure_buttons,
    admin_workflow_buttons,
    ATTENDANCE_REASON_LABELS,
    approval_card_buttons,
    approvals_menu_buttons,
    attendance_reason_buttons,
    employee_case_buttons,
    employee_manager_section_buttons,
    employee_personal_buttons,
    employee_reason_section_buttons,
    hr_reference_buttons,
    hr_reports_buttons,
    hr_settings_buttons,
    hr_workflow_buttons,
    manager_management_buttons,
    manager_reports_buttons,
    manager_workflow_buttons,
    main_menu_buttons,
    reports_menu_buttons,
    security_audit_buttons,
    security_skud_buttons,
    top_reports_buttons,
    top_summary_buttons,
    top_workflow_buttons,
    substitutions_menu_buttons,
)
from app.bot.menus import get_menu_for_role
from app.domain.enums import ApprovalStatus, AttendanceCaseStatus, DialogFlow, Role
from app.domain.dialog_state import UserDialogState
from app.domain.role_labels import display_role_name
from app.integrations.max.client import MaxApiClient
from app.integrations.google_sheets.directory import GoogleSheetsDirectoryService
from app.repositories.approval_repository import ApprovalRepository
from app.repositories.attendance_case_repository import AttendanceCaseRepository
from app.repositories.employee_directory_repository import EmployeeDirectoryRepository
from app.services.report_service import ReportService
from app.repositories.skud_import_repository import SkudImportRepository
from app.repositories.substitution_repository import SubstitutionRepository
from app.repositories.user_role_override_repository import UserRoleOverrideRepository
from app.schemas.max import MaxOutboundButton, MaxOutboundMessage, MaxUpdate, MaxWebhookResponse
from app.services.dialog_state import dialog_state_store
from app.services.max_file_import import MaxFileImportService
from app.services.role_resolver import RoleResolver
from app.services.substitution_flow import SubstitutionFlowService


class MaxWebhookRouter:
    def __init__(self) -> None:
        self.role_resolver = RoleResolver()
        self.substitution_flow = SubstitutionFlowService()
        self.substitution_repository = SubstitutionRepository()
        self.case_repository = AttendanceCaseRepository()
        self.approval_repository = ApprovalRepository()
        self.google_directory_service = GoogleSheetsDirectoryService.from_settings()
        self.employee_directory_repository = EmployeeDirectoryRepository()
        self.report_service = ReportService()
        self.skud_import_repository = SkudImportRepository()
        self.user_role_override_repository = UserRoleOverrideRepository()
        self.max_client = MaxApiClient.from_settings()
        self.max_file_import_service = MaxFileImportService()
        self.logger = logging.getLogger(__name__)

    def handle_event(self, payload: MaxUpdate) -> MaxWebhookResponse:
        event = self._normalize_event(payload)
        role = self.role_resolver.resolve_role(
            user_id=event["user_id"],
            chat_id=event["chat_id"],
        )
        action = event["action"]
        user_text = event["text"]
        active_state = dialog_state_store.get(event["user_id"])

        if self._is_main_menu_action(action, user_text):
            dialog_state_store.reset(event["user_id"])
            response = self._menu_response(role, "Главное меню готово.")
            self._send_outbound(payload, response.outbound)
            return response

        if active_state and active_state.flow == DialogFlow.SUBSTITUTION.value:
            result = self.substitution_flow.handle_input(event["user_id"], role, user_text, action, active_state)
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

        if action == BotAction.WHOAMI or user_text == "Кто я" or user_text == "/whoami":
            response = self._whoami(role, event["user_id"], event["chat_id"])
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
            response = self._menu_response(target_role, "Роль переключена на: {0}".format(display_role_name(target_role)))
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.EMPLOYEE_PERSONAL:
            response = self._employee_personal_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.EMPLOYEE_REASONS:
            response = self._employee_reason_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.EMPLOYEE_MANAGER:
            response = self._employee_manager_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MANAGER_MANAGEMENT:
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

        if action == BotAction.SECURITY_SKUD:
            response = self._security_skud_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.SECURITY_AUDIT:
            response = self._security_audit_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.HR_REFERENCE:
            response = self._hr_reference_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.HR_WORKFLOW:
            response = self._hr_workflow_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.HR_REPORTS:
            response = self._hr_reports_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.HR_SETTINGS:
            response = self._hr_settings_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.TOP_SUMMARY:
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

        if action == BotAction.MENU_SUBMIT_REASON or user_text == "Указать причину":
            response = self._employee_pending_reason_cases(role, event["user_id"])
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

        if action == BotAction.MENU_EMPLOYEES or user_text == "Мои сотрудники":
            response = self._manager_employees(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_DEPARTMENT_LATES or user_text == "Опоздания отдела":
            response = self._department_cases(role, event["user_id"], AttendanceCaseStatus.AWAITING_EMPLOYEE_REASON.value)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_DEPARTMENT_ABSENCES or user_text == "Неявки отдела":
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

        if action == BotAction.MENU_REPORTS or user_text == "Отчеты":
            response = self._reports_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_SUMMARY or user_text == "Сводка":
            response = self._summary_menu(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_DIVISION_REPORTS or user_text == "Отчеты по подразделениям":
            response = self._division_reports(role, event["user_id"], event["chat_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_OVERDUE_APPROVALS or user_text == "Просроченные согласования":
            response = self._overdue_approvals(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_SECURITY_IMPORT or user_text == "Загрузить выгрузку СКУД":
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

        if action == BotAction.MENU_SCHEDULES or user_text == "Графики":
            response = self._schedules_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_EXCEPTIONS or user_text == "Исключения":
            response = self._exceptions_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_SETTINGS or user_text == "Системные настройки":
            response = self._settings_menu(role)
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

        if action == BotAction.ADMIN_PERSONAL:
            response = self._admin_personal_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.ADMIN_STRUCTURE:
            response = self._admin_structure_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.ADMIN_SKUD:
            response = self._admin_skud_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.ADMIN_WORKFLOW:
            response = self._admin_workflow_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.ADMIN_REPORTS:
            response = self._admin_reports_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.ADMIN_SETTINGS:
            response = self._admin_settings_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_MY_ROW or user_text == "Моя строка":
            response = self._my_row(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_BINDING_CHECK or user_text == "Проверить привязку":
            response = self._binding_check(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_MATCH_ERRORS or user_text == "Ошибки сопоставления":
            response = self._match_errors_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_UNPROCESSED or user_text == "Необработанные записи":
            response = self._unprocessed_menu(role)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.SUBSTITUTION_CREATE or user_text == "Назначить замещение":
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

        if action.startswith(BotAction.SUBSTITUTION_EXTEND_PREFIX):
            draft_id = self._parse_id(action, BotAction.SUBSTITUTION_EXTEND_PREFIX)
            response = self._start_substitution_extend_flow(role, event["user_id"], draft_id)
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.SUBSTITUTION_LIST:
            response = self._substitution_list(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.SUBSTITUTION_CANCEL:
            response = self._substitution_cancel(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.SUBSTITUTION_EXTEND:
            response = self._substitution_extend(role, event["user_id"])
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
            self.approval_repository.update_status(approval_id, ApprovalStatus.APPROVED.value)
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
            self.approval_repository.update_status(approval_id, ApprovalStatus.REJECTED.value)
            response = self._approvals_list(
                role,
                event["user_id"],
                BotAction.APPROVALS_IN_PROGRESS,
                prefix_text="Согласование #{0} отклонено.\n\n".format(approval_id),
            )
            self._send_outbound(payload, response.outbound)
            return response

        if action.startswith(BotAction.EMPLOYEE_CASE_OPEN_PREFIX):
            case_id = self._parse_id(action, BotAction.EMPLOYEE_CASE_OPEN_PREFIX)
            response = self._employee_case_card(role, event["user_id"], case_id)
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
                if role != Role.SECURITY.value:
                    response = self._stub_section(role, "Загрузка файлов доступна только службе безопасности.")
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
                            MaxOutboundButton(title="Загрузить выгрузку СКУД", action=BotAction.MENU_SECURITY_IMPORT),
                            MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                        ],
                    ),
                    active_flow=None,
                )
                self._send_outbound(payload, response.outbound)
                return response

        menu = get_menu_for_role(role)
        message = MaxOutboundMessage(
            text="Роль определена как: {role}. Кнопка `{text}` пока подключена как заглушка.".format(
                role=display_role_name(role),
                text=user_text or action or "без текста",
            ),
            buttons=main_menu_buttons(role),
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

    def _menu_response(self, role: str, text: str) -> MaxWebhookResponse:
        menu = get_menu_for_role(role)
        prefix = ""
        if role == Role.ADMIN.value:
            prefix = "Администратор. Источник прав: Google Sheets.\n\n"
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=menu,
            outbound=MaxOutboundMessage(text=prefix + text, buttons=main_menu_buttons(role)),
            active_flow=None,
        )

    def _employee_personal_menu(self, role: str) -> MaxWebhookResponse:
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Личный раздел сотрудника.",
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
                text="Раздел причин и опозданий.",
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

    def _manager_management_menu(self, role: str) -> MaxWebhookResponse:
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Управление сотрудниками и нарушениями.",
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
                text="Отчетный блок руководителя.",
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
                text="Процессы согласований и замещений.",
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
                text="Раздел СКУД.",
                buttons=security_skud_buttons(),
            ),
            active_flow=None,
        )

    def _security_audit_menu(self, role: str) -> MaxWebhookResponse:
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Журнал и очередь разборов.",
                buttons=security_audit_buttons(),
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

    def _hr_settings_menu(self, role: str) -> MaxWebhookResponse:
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Параметры HR.",
                buttons=hr_settings_buttons(),
            ),
            active_flow=None,
        )

    def _top_summary_menu(self, role: str) -> MaxWebhookResponse:
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Аналитика верхнего уровня.",
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
                text="Отчетный блок верхнего уровня.",
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
            outbound=MaxOutboundMessage(text="Раздел замещений. Выбери действие.", buttons=buttons),
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
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="История импортов", action=BotAction.MENU_IMPORT_HISTORY),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
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

        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU)],
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
                    MaxOutboundButton(title="Мои опоздания", action=BotAction.MENU_MY_LATES),
                    MaxOutboundButton(title="Мои статусы", action=BotAction.MENU_MY_STATUSES),
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
                    MaxOutboundButton(title="Мои уведомления", action=BotAction.MENU_MY_NOTIFICATIONS),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _manager_employees(self, role: str, user_id: str) -> MaxWebhookResponse:
        directory_rows = self._resolve_directory_rows_by_manager_user_id(user_id)
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
            case_rows = self.case_repository.list_for_manager_user(user_id, limit=10)
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
                    MaxOutboundButton(title="Опоздания отдела", action=BotAction.MENU_DEPARTMENT_LATES),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _department_cases(self, role: str, user_id: str, status_hint: str) -> MaxWebhookResponse:
        rows = self.case_repository.list_for_manager_user(user_id, limit=20)
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
                    MaxOutboundButton(title="Отчеты", action=BotAction.MENU_REPORTS),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _summary_menu(self, role: str, user_id: str) -> MaxWebhookResponse:
        approvals = self.approval_repository.count_pending_for_manager(user_id)
        cases = self.case_repository.count_for_manager_user(
            user_id,
            statuses=[
                AttendanceCaseStatus.AWAITING_EMPLOYEE_REASON.value,
                AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value,
            ],
        )
        text = (
            "Сводка:\n\n"
            "Ожидают согласования: {approvals}\n"
            "Активных случаев по твоим сотрудникам: {cases}"
        ).format(approvals=approvals, cases=cases)
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Просроченные согласования", action=BotAction.MENU_OVERDUE_APPROVALS),
                    MaxOutboundButton(title="Отчеты по подразделениям", action=BotAction.MENU_DIVISION_REPORTS),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _division_reports(self, role: str, user_id: str, chat_id: str) -> MaxWebhookResponse:
        artifact = self.report_service.generate_division_report(user_id=user_id, role=role, period="month")
        self._queue_report_files(chat_id, user_id, artifact.title, artifact.file_path, artifact.pdf_file_path)
        text = (
            "Отчет по подразделениям готов.\n\n"
            "{summary}\n\n"
            "Я уже отправил его в чат."
        ).format(
            summary=artifact.summary_text,
        )

        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Недельный отчет", action=BotAction.REPORT_WEEK),
                    MaxOutboundButton(title="Месячный отчет", action=BotAction.REPORT_MONTH),
                    MaxOutboundButton(title="Квартальный отчет", action=BotAction.REPORT_QUARTER),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _overdue_approvals(self, role: str, user_id: str) -> MaxWebhookResponse:
        rows = self.approval_repository.list_overdue_for_manager(user_id)
        if not rows:
            text = "Просроченных согласований нет."
            buttons = [MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU)]
        else:
            lines = [
                "#{approval_id} | {employee} | {date} | {kind}".format(
                    approval_id=approval.id,
                    employee=case.employee_name,
                    date=case.event_date,
                    kind="Опоздание" if case.case_type == "late" else "Неявка",
                )
                for approval, case in rows[:10]
            ]
            text = "Просроченные согласования:\n\n" + "\n".join(lines)
            buttons = [MaxOutboundButton(title="Согласования", action=BotAction.MENU_APPROVALS), MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU)]

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
        artifact = self.report_service.generate_manager_report(user_id=user_id, role=role, period=period)
        self._queue_report_files(chat_id, user_id, artifact.title, artifact.file_path, artifact.pdf_file_path)
        text = (
            "{title} готов.\n\n"
            "{summary}\n\n"
            "Я уже отправил его в чат."
        ).format(
            title=label.capitalize(),
            summary=artifact.summary_text,
        )
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
            buttons=[
                MaxOutboundButton(title="Сводка", action=BotAction.MENU_SUMMARY),
                MaxOutboundButton(title="Отчеты по подразделениям", action=BotAction.MENU_DIVISION_REPORTS),
                MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
            ],
            ),
            active_flow=None,
        )

    def _substitution_cancel(self, role: str, user_id: str) -> MaxWebhookResponse:
        rows = self.substitution_repository.list_drafts_for_user(user_id)
        if not rows:
            text = "У тебя нет черновиков замещений для отмены."
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
            text = "Выбери черновик для отмены:\n\n" + "\n".join(lines)
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

    def _substitution_extend(self, role: str, user_id: str) -> MaxWebhookResponse:
        rows = self.substitution_repository.list_drafts_for_user(user_id)
        if not rows:
            text = "У тебя нет черновиков замещений для продления."
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
                    MaxOutboundButton(title="История импортов", action=BotAction.MENU_IMPORT_HISTORY),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
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

    def _resolve_directory_record_by_user_id(self, user_id: str):
        google_record = self.google_directory_service.get_by_user_id(user_id)
        if google_record is not None:
            return google_record
        return self.employee_directory_repository.get_by_user_id(user_id)

    def _resolve_directory_rows_by_manager_user_id(self, manager_user_id: str):
        google_rows = self.google_directory_service.get_by_manager_user_id(manager_user_id)
        if google_rows:
            return google_rows
        return self.employee_directory_repository.get_by_manager_user_id(manager_user_id)

    def _resolve_directory_rows_recent(self, limit: int = 50):
        google_rows = self.google_directory_service.list_employees()
        if google_rows:
            return google_rows[:limit]
        return self.employee_directory_repository.list_recent(limit=limit)

    def _schedules_menu(self, role: str) -> MaxWebhookResponse:
        text = (
            "Раздел графиков готов к заполнению.\n\n"
            "Текущий основной график в боте: 08:30 - 18:00, понедельник-пятница.\n"
            "Фактический справочник графиков подключим следующим шагом."
        )
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Исключения", action=BotAction.MENU_EXCEPTIONS),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _exceptions_menu(self, role: str) -> MaxWebhookResponse:
        text = (
            "Исключения сейчас ведутся через импорт справочника и будущий CRUD.\n\n"
            "Поддерживаемые типы: отпуск, больничный, командировка, удаленная работа, разрешенное опоздание."
        )
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Графики", action=BotAction.MENU_SCHEDULES),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _settings_menu(self, role: str) -> MaxWebhookResponse:
        text = (
            "Системные настройки:\n\n"
            "Порог опоздания: 10 минут\n"
            "Неявка после: 12:00\n"
            "Срок ответа сотрудника: 1 рабочий день\n"
            "Срок согласования: 1 рабочий день"
        )
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
                    MaxOutboundButton(title="Системные настройки", action=BotAction.MENU_SETTINGS),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _admin_panel_menu(self, role: str, user_id: str) -> MaxWebhookResponse:
        if role != Role.ADMIN.value:
            return self._stub_section(role, "Админ-панель доступна только администратору.")

        sheet_record = self.google_directory_service.get_by_user_id(user_id)
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

    def _admin_settings_menu(self, role: str) -> MaxWebhookResponse:
        if role != Role.ADMIN.value:
            return self._stub_section(role, "Раздел настроек доступен только администратору.")
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Системные настройки и параметры контроля.",
                buttons=admin_settings_buttons(),
            ),
            active_flow=None,
        )

    def _whoami(self, role: str, user_id: str, chat_id: str) -> MaxWebhookResponse:
        sheet_record = self.google_directory_service.get_by_user_id(user_id)
        if sheet_record is not None:
            sheet_status = (
                "Найдено в Google Sheets.\n"
                "ФИО: {name}\n"
                "Роль в таблице: {sheet_role}\n"
                "Активен: {active}\n"
                "Руководитель: {manager}\n"
                "Подразделение: {department}"
            ).format(
                name=sheet_record.employee_name or "-",
                sheet_role=display_role_name(sheet_record.role or "-"),
                active="Да" if sheet_record.is_active else "Нет",
                manager=sheet_record.manager_name or "-",
                department=sheet_record.department_name or "-",
            )
            needed_id = sheet_record.employee_user_id or user_id
        else:
            sheet_status = "В Google Sheets по этому user_id запись не найдена."
            needed_id = user_id

        text = (
            "Кто я:\n\n"
            "Твой ID в MAX: {user_id}\n"
            "Чат: {chat_id}\n"
            "Роль в боте: {role}\n\n"
            "{sheet_status}\n\n"
            "Чтобы бот показал админ-панель, в таблице `Сотрудники` у тебя должен быть тот же ID в MAX.\n"
            "Нужный ID для таблицы: {needed_id}"
        ).format(
            user_id=user_id,
            chat_id=chat_id,
            role=display_role_name(role),
            sheet_status=sheet_status,
            needed_id=needed_id,
        )
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Админ-панель", action=BotAction.MENU_ADMIN_PANEL),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _my_row(self, role: str, user_id: str) -> MaxWebhookResponse:
        sheet_record = self.google_directory_service.get_by_user_id(user_id)
        if sheet_record is None:
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
                "Руководитель: {manager}\n"
                "Активен: {active}"
            ).format(
                name=sheet_record.employee_name or "-",
                user_id=sheet_record.employee_user_id or "-",
                role=display_role_name(sheet_record.role or "-"),
                department=sheet_record.department_name or "-",
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
                    MaxOutboundButton(title="Кто я", action=BotAction.WHOAMI),
                    MaxOutboundButton(title="Админ-панель", action=BotAction.MENU_ADMIN_PANEL),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _binding_check(self, role: str, user_id: str) -> MaxWebhookResponse:
        sheet_record = self.google_directory_service.get_by_user_id(user_id)
        if sheet_record is None:
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

    def _match_errors_menu(self, role: str) -> MaxWebhookResponse:
        text = (
            "Ошибки сопоставления пока не ведутся как отдельный журнал.\n\n"
            "Когда справочник сотрудников и MAX ID будут заполнены, здесь появятся строки, которые не удалось связать."
        )
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="История импортов", action=BotAction.MENU_IMPORT_HISTORY),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _unprocessed_menu(self, role: str) -> MaxWebhookResponse:
        text = (
            "Необработанные записи сейчас отсутствуют в отдельном журнале.\n\n"
            "После загрузки справочника и расширения импорта этот раздел можно будет подключить к очереди разборов."
        )
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Загрузить выгрузку СКУД", action=BotAction.MENU_SECURITY_IMPORT),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

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

        text = "Файл принят. Вот что получилось:\n\n" + "\n\n".join(result.message for result in results)
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="История импортов", action=BotAction.MENU_IMPORT_HISTORY),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
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
        rows = self.case_repository.list_for_employee_user(user_id)
        if not rows:
            text = (
                "У тебя пока нет зарегистрированных случаев.\n\n"
                "Если справочник сотрудников еще не загружен, сначала импортируй его через раздел `Сотрудники`."
            )
            buttons = [
                MaxOutboundButton(title="Мои уведомления", action=BotAction.MENU_MY_NOTIFICATIONS),
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
                        kind="Опоздание" if case.case_type == "late" else "Неявка",
                        status=self._status_label(case.status),
                    )
                )
                buttons.append(
                    MaxOutboundButton(
                        title="Открыть #{0}".format(case.id),
                        action="{0}{1}".format(BotAction.EMPLOYEE_CASE_OPEN_PREFIX, case.id),
                    )
                )
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
        rows = self.case_repository.list_pending_reason_for_employee(user_id)
        if not rows:
            return MaxWebhookResponse(
                ok=True,
                role=role,
                menu=get_menu_for_role(role),
                outbound=MaxOutboundMessage(
                    text="У тебя нет случаев, где требуется указать причину.",
                    buttons=[MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU)],
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
                    kind="Опоздание" if case.case_type == "late" else "Неявка",
                )
            )
            buttons.append(
                MaxOutboundButton(
                    title="Указать по #{0}".format(case.id),
                    action="{0}{1}".format(BotAction.EMPLOYEE_CASE_OPEN_PREFIX, case.id),
                )
            )
        buttons.append(MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU))
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text="Выбери случай для указания причины:\n\n{0}".format("\n".join(lines)),
                buttons=buttons,
            ),
            active_flow=None,
        )

    def _employee_case_statuses(self, role: str, user_id: str) -> MaxWebhookResponse:
        rows = self.case_repository.list_for_employee_user(user_id)
        if not rows:
            return self._employee_cases(role, user_id)

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
                buttons=[MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU)],
            ),
            active_flow=None,
        )

    def _stub_section(self, role: str, text: str) -> MaxWebhookResponse:
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                    MaxOutboundButton(title="Замещения", action=BotAction.MENU_SUBSTITUTIONS),
                ],
            ),
            active_flow=None,
        )

    def _approvals_list(self, role: str, user_id: str, action: str, prefix_text: str = "") -> MaxWebhookResponse:
        if action == BotAction.APPROVALS_HISTORY:
            rows = self.approval_repository.list_for_manager(
                user_id,
                statuses=[ApprovalStatus.APPROVED.value, ApprovalStatus.REJECTED.value],
            )
            heading = "История согласований"
        elif action == BotAction.APPROVALS_OVERDUE:
            rows = self.approval_repository.list_overdue_for_manager(user_id)
            heading = "Просроченные согласования"
        else:
            rows = self.approval_repository.list_for_manager(user_id, statuses=[ApprovalStatus.PENDING.value])
            heading = "Согласования в ожидании"

        if not rows:
            text = prefix_text + "У тебя нет согласований в этом разделе."
            buttons = [MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU)]
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
                        kind="Опоздание" if case.case_type == "late" else "Неявка",
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
            buttons.append(MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU))
            text = prefix_text + "{heading}:\n\n{lines}".format(heading=heading, lines="\n".join(lines))

        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(text=text, buttons=buttons),
            active_flow=None,
        )

    def _approval_card(self, role: str, user_id: str, approval_id: int) -> MaxWebhookResponse:
        rows = self.approval_repository.list_pending_for_manager(user_id)
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
            kind="Опоздание" if case.case_type == "late" else "Неявка",
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
        text = (
            "Случай #{id}\n\n"
            "Дата: {date}\n"
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
            kind="Опоздание" if case.case_type == "late" else "Неявка",
            department=case.department_name,
            planned=case.planned_start,
            actual=case.actual_start,
            delay=case.delay_minutes,
            status=self._status_label(case.status),
            reason=case.employee_reason or "-",
        )
        if require_reason:
            buttons = [
                MaxOutboundButton(title="Выбрать руководителя", action=f"{BotAction.EMPLOYEE_REASON_START_PREFIX}{case.id}", emoji="👔", row=0),
                MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=1),
            ]
        else:
            buttons = employee_case_buttons(case.id, require_reason=False)
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(text=text, buttons=buttons),
            active_flow=None,
        )

    def _start_attendance_reason_flow(self, role: str, user_id: str, case_id: int) -> MaxWebhookResponse:
        case = self.case_repository.get(case_id)
        if case is None or case.employee_user_id != user_id:
            return self._stub_section(role, "Случай #{0} не найден.".format(case_id))

        candidates = self._resolve_reason_manager_options(case)
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
        options: List[Tuple[str, str]] = []
        seen: set[str] = set()

        def add_option(manager_user_id: str, manager_name: str) -> None:
            manager_user_id = str(manager_user_id or "").strip()
            manager_name = str(manager_name or "").strip() or "Руководитель"
            if not manager_user_id or manager_user_id in seen:
                return
            seen.add(manager_user_id)
            options.append((manager_user_id, manager_name))

        if case.manager_user_id:
            add_option(case.manager_user_id, case.manager_name or "Руководитель")

        directory_rows = self._resolve_directory_rows_recent(limit=200)
        case_department = str(case.department_name or "").strip().lower()
        for row in directory_rows:
            if not row.is_active:
                continue
            if row.role not in {Role.MANAGER.value, Role.ADMIN.value, Role.TOP_MANAGER.value}:
                continue
            row_department = str(getattr(row, "department_name", "") or "").strip().lower()
            if case_department and row_department and row_department != case_department:
                continue
            add_option(row.employee_user_id, row.employee_name or row.manager_name or "Руководитель")

        return options

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
                buttons=[MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0)],
            ),
            active_flow=DialogFlow.ATTENDANCE_REASON.value,
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
                    MaxOutboundButton(title="Мои статусы", action=BotAction.MENU_MY_STATUSES),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _notify_manager_about_reason(self, case, reason_label: str, approval_id: int | None) -> None:
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
            kind="Опоздание" if case.case_type == "late" else "Неявка",
            delay=case.delay_minutes,
            reason=reason_label,
        )
        buttons = approval_card_buttons(approval_id) if approval_id else [MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0)]
        try:
            self.max_client.send_message(
                user_id=case.manager_user_id,
                text=approval_text,
                buttons=buttons,
            )
        except Exception:
            return

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
                MaxOutboundButton(title="Назначить замещение", action=BotAction.SUBSTITUTION_CREATE, emoji="➕", row=0),
                MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=0),
            ]
        else:
            preview_lines = []
            for row in rows[:5]:
                preview_lines.append(
                    "#{id}: {target} -> {replacement} | {date_from} - {date_to} | {scope}".format(
                        id=row.id,
                        target=row.target_manager,
                        replacement=row.replacement_user,
                        date_from=row.date_from,
                        date_to=row.date_to,
                        scope=row.scope,
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
                text="Черновик #{0} отменен.\n\nМои замещения:\n\n{1}".format(
                    draft_id,
                    "\n".join(
                        "#{id}: {target} -> {replacement} | {date_from} - {date_to} | {scope} | {status}".format(
                            id=row.id,
                            target=row.target_manager,
                            replacement=row.replacement_user,
                            date_from=row.date_from,
                            date_to=row.date_to,
                            scope=row.scope,
                            status=row.status,
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
                        title=f"Отменить #{row.id}",
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
                        title=f"Отменить #{row.id}",
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

        buttons.append(MaxOutboundButton(title="Назначить замещение", action=BotAction.SUBSTITUTION_CREATE, emoji="➕", row=10))
        buttons.append(MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU, emoji="🏠", row=10))
        return buttons

    def _send_outbound(self, inbound: MaxUpdate, outbound: MaxOutboundMessage) -> None:
        if not self.max_client.is_configured():
            return

        try:
            if inbound.update_type == "message_callback" and inbound.callback:
                callback_action = inbound.callback.payload or ""
                if self._is_main_menu_action(callback_action, ""):
                    recipients = self._outbound_recipients(inbound)
                    for recipient_type, recipient_value in recipients:
                        try:
                            if recipient_type == "chat_id":
                                self.max_client.send_message(
                                    chat_id=recipient_value,
                                    text=outbound.text,
                                    buttons=outbound.buttons,
                                )
                            else:
                                self.max_client.send_message(
                                    user_id=recipient_value,
                                    text=outbound.text,
                                    buttons=outbound.buttons,
                                )
                            break
                        except Exception:
                            continue
                self.max_client.answer_callback(
                    callback_id=inbound.callback.callback_id,
                    notification="Главное меню открыто" if self._is_main_menu_action(callback_action, "") else None,
                    new_text=outbound.text if self._is_main_menu_action(callback_action, "") else outbound.text,
                    buttons=outbound.buttons if self._is_main_menu_action(callback_action, "") else outbound.buttons,
                )
                return

            if inbound.update_type in {"bot_started", "message_created"}:
                recipients = self._outbound_recipients(inbound)
                last_error: Exception | None = None
                for recipient_type, recipient_value in recipients:
                    try:
                        if recipient_type == "chat_id":
                            self.max_client.send_message(
                                chat_id=recipient_value,
                                text=outbound.text,
                                buttons=outbound.buttons,
                            )
                        else:
                            self.max_client.send_message(
                                user_id=recipient_value,
                                text=outbound.text,
                                buttons=outbound.buttons,
                            )
                        return
                    except Exception as exc:
                        last_error = exc
                        continue
                if last_error is not None:
                    raise last_error
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

    def _send_report_files(self, chat_id: str, user_id: str, title: str, xlsx_path: str, pdf_path: str) -> None:
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
                        self.max_client.send_file_message(
                            chat_id=recipient_value,
                            text=f"{title} в Excel",
                            file_path=xlsx_path,
                        )
                        self.max_client.send_file_message(
                            chat_id=recipient_value,
                            text=f"{title} в PDF",
                            file_path=pdf_path,
                        )
                    else:
                        self.max_client.send_file_message(
                            user_id=recipient_value,
                            text=f"{title} в Excel",
                            file_path=xlsx_path,
                        )
                        self.max_client.send_file_message(
                            user_id=recipient_value,
                            text=f"{title} в PDF",
                            file_path=pdf_path,
                        )
                    return
                except Exception:
                    continue
        except Exception:
            self.logger.exception(
                "Failed to send MAX report files chat_id=%s user_id=%s title=%s",
                chat_id,
                user_id,
                title,
            )
            return

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
        if inbound.chat_id is not None:
            recipients.append(("chat_id", int(inbound.chat_id)))
        recipient_chat_id = getattr(inbound.message.recipient, "chat_id", None) if inbound.message else None
        if recipient_chat_id is not None:
            recipients.append(("chat_id", int(recipient_chat_id)))
        if inbound.user and inbound.user.user_id is not None:
            recipients.append(("user_id", int(inbound.user.user_id)))
        if inbound.message and inbound.message.sender and inbound.message.sender.user_id is not None:
            recipients.append(("user_id", int(inbound.message.sender.user_id)))

        unique: list[tuple[str, int]] = []
        seen = set()
        for recipient in recipients:
            if recipient in seen:
                continue
            seen.add(recipient)
            unique.append(recipient)
        return unique

    def _approval_status_label(self, status: str) -> str:
        labels = {
            ApprovalStatus.PENDING.value: "Ожидает",
            ApprovalStatus.APPROVED.value: "Согласовано",
            ApprovalStatus.REJECTED.value: "Отклонено",
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
            cls._normalize_navigation_action("Главное меню"),
            cls._normalize_navigation_action("menu_main"),
            cls._normalize_navigation_action("main_menu"),
            cls._normalize_navigation_action("главноеменю"),
        } or normalized_text in {
            cls._normalize_navigation_action(BotAction.START),
            cls._normalize_navigation_action("/start"),
            cls._normalize_navigation_action("Старт"),
            cls._normalize_navigation_action("Главное меню"),
            cls._normalize_navigation_action("menu_main"),
            cls._normalize_navigation_action("main_menu"),
            cls._normalize_navigation_action("главноеменю"),
        }
