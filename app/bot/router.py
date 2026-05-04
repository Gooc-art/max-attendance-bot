from __future__ import annotations

from typing import List

from app.bot.actions import BotAction
from app.bot.buttons import (
    ATTENDANCE_REASON_LABELS,
    approval_card_buttons,
    approvals_menu_buttons,
    attendance_reason_buttons,
    employee_case_buttons,
    main_menu_buttons,
    reports_menu_buttons,
    substitutions_menu_buttons,
)
from app.bot.menus import get_menu_for_role
from app.domain.enums import ApprovalStatus, AttendanceCaseStatus, DialogFlow, Role
from app.integrations.max.client import MaxApiClient
from app.integrations.google_sheets.directory import GoogleSheetsDirectoryService
from app.repositories.approval_repository import ApprovalRepository
from app.repositories.attendance_case_repository import AttendanceCaseRepository
from app.repositories.employee_directory_repository import EmployeeDirectoryRepository
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
        self.skud_import_repository = SkudImportRepository()
        self.user_role_override_repository = UserRoleOverrideRepository()
        self.max_client = MaxApiClient.from_settings()
        self.max_file_import_service = MaxFileImportService()

    def handle_event(self, payload: MaxUpdate) -> MaxWebhookResponse:
        event = self._normalize_event(payload)
        role = self.role_resolver.resolve_role(
            user_id=event["user_id"],
            chat_id=event["chat_id"],
        )
        action = event["action"]
        user_text = event["text"]
        active_state = dialog_state_store.get(event["user_id"])

        if payload.message and payload.message.body.attachments:
            response = self._handle_attachments(role, event["user_id"], payload.message.body.attachments)
            if response is not None:
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

        if action in {BotAction.START, BotAction.MAIN_MENU, "/start", "Главное меню"}:
            dialog_state_store.reset(event["user_id"])
            response = self._menu_response(role, "Главное меню готово.")
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
            response = self._menu_response(target_role, "Роль переключена на: {0}".format(target_role))
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
            response = self._division_reports(role, event["user_id"])
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
            response = self._quick_report(role, event["user_id"], action)
            self._send_outbound(payload, response.outbound)
            return response

        menu = get_menu_for_role(role)
        message = MaxOutboundMessage(
            text="Роль определена как: {role}. Кнопка `{text}` пока подключена как заглушка.".format(
                role=role,
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

        if payload.update_type == "message_callback" and payload.callback and payload.message:
            return {
                "user_id": str(payload.callback.user.user_id),
                "chat_id": str(payload.message.recipient.chat_id),
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
        text = (
            "Импорт СКУД сейчас подключен через API.\n\n"
            "POST /api/imports/skud/csv?filename=prohodki.csv&created_by_user_id={user_id}\n"
            "Body: сырой CSV файл.\n\n"
            "Можно отправить запрос через Swagger /docs или curl."
        ).format(user_id=user_id)
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
            text = "История импортов пока пустая."
        else:
            text = "Последние импорты:\n\n" + "\n".join(
                "#{id} | {filename} | {period_start} - {period_end} | сотрудников: {employees} | создано: {created} | ошибок: {errors} | {status}".format(
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
                role=record.role or "employee",
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

    def _division_reports(self, role: str, user_id: str) -> MaxWebhookResponse:
        rows = self.case_repository.list_for_manager_user(user_id, limit=50)
        if not rows:
            text = "Отчеты по подразделениям пока пустые."
        else:
            late = sum(1 for case in rows if case.case_type == "late")
            absent = sum(1 for case in rows if case.case_type == "absent")
            justified = sum(1 for case in rows if case.status == AttendanceCaseStatus.JUSTIFIED.value)
            text = (
                "Отчеты по подразделениям:\n\n"
                "Опоздания: {late}\n"
                "Неявки: {absent}\n"
                "Подтверждено уважительно: {justified}\n"
                "Всего случаев: {total}"
            ).format(late=late, absent=absent, justified=justified, total=len(rows))

        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Недельный отчет", action=BotAction.REPORT_WEEK),
                    MaxOutboundButton(title="Месячный отчет", action=BotAction.REPORT_MONTH),
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

    def _quick_report(self, role: str, user_id: str, action: str) -> MaxWebhookResponse:
        rows = self.case_repository.list_for_manager_user(user_id, limit=100)
        label = {
            BotAction.REPORT_WEEK: "недельный",
            BotAction.REPORT_MONTH: "месячный",
            BotAction.REPORT_QUARTER: "квартальный",
        }.get(action, "выбранный")
        if not rows:
            text = "{0} отчет пока пустой.".format(label.capitalize())
        else:
            text = (
                "{title} отчет:\n\n"
                "Всего случаев: {total}\n"
                "Опоздания: {late}\n"
                "Неявки: {absent}\n"
                "На согласовании: {pending}"
            ).format(
                title=label.capitalize(),
                total=len(rows),
                late=sum(1 for case in rows if case.case_type == "late"),
                absent=sum(1 for case in rows if case.case_type == "absent"),
                pending=sum(1 for case in rows if case.status == AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value),
            )
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Сводка", action=BotAction.MENU_SUMMARY),
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
            latest = rows[0]
            text = (
                "Последний черновик замещения #{id} можно отменить на следующем этапе CRUD.\n\n"
                "Сейчас доступны:\n"
                "Кого замещаем: {target}\n"
                "Кто замещает: {replacement}\n"
                "Период: {date_from} - {date_to}"
            ).format(
                id=latest.id,
                target=latest.target_manager,
                replacement=latest.replacement_user,
                date_from=latest.date_from,
                date_to=latest.date_to,
            )
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Мои замещения", action=BotAction.SUBSTITUTION_LIST),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _substitution_extend(self, role: str, user_id: str) -> MaxWebhookResponse:
        rows = self.substitution_repository.list_drafts_for_user(user_id)
        if not rows:
            text = "У тебя нет черновиков замещений для продления."
        else:
            latest = rows[0]
            text = (
                "Продление замещения на следующем шаге будет работать как редактирование периода.\n\n"
                "Текущий черновик #{id}: {date_from} - {date_to}."
            ).format(id=latest.id, date_from=latest.date_from, date_to=latest.date_to)
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Мои замещения", action=BotAction.SUBSTITUTION_LIST),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _staff_menu(self, role: str) -> MaxWebhookResponse:
        rows = self._resolve_directory_rows_recent(limit=8)
        if not rows:
            text = (
                "Справочник сотрудников пока пустой.\n\n"
                "Загрузить можно через API:\n"
                "POST /api/employees/directory/csv"
            )
        else:
            text = "Последние сотрудники:\n\n" + "\n".join(
                "#{id} | {name} | {user_id} | {role} | {dept}".format(
                    id=row.id,
                    name=row.employee_name,
                    user_id=row.employee_user_id,
                    role=row.role,
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
                "Они появятся после импорта справочника сотрудников."
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
                    role=row.role,
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

    def _handle_attachments(self, role: str, user_id: str, attachments: list) -> MaxWebhookResponse | None:
        file_attachments = [attachment for attachment in attachments if getattr(attachment, "type", "") == "file"]
        if not file_attachments:
            return None

        results = self.max_file_import_service.import_attachments(file_attachments, created_by_user_id=user_id)
        if not results:
            return None

        text = "Результат обработки вложений:\n\n" + "\n\n".join(result.message for result in results)
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
        buttons = attendance_reason_buttons(case.id) if require_reason else employee_case_buttons(case.id, require_reason=False)
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(text=text, buttons=buttons),
            active_flow=None,
        )

    def _employee_submit_reason(self, role: str, user_id: str, action: str) -> MaxWebhookResponse:
        _, remainder = action.split(BotAction.EMPLOYEE_REASON_PREFIX, 1)
        case_part, reason_code = remainder.split(":", 1)
        case_id = int(case_part)
        case = self.case_repository.get(case_id)
        if case is None or case.employee_user_id != user_id:
            return self._stub_section(role, "Случай #{0} не найден.".format(case_id))

        reason_label = ATTENDANCE_REASON_LABELS.get(reason_code, reason_code)
        self.case_repository.update_reason_and_status(
            case_id=case_id,
            employee_reason=reason_label,
            status=AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value,
        )
        if case.manager_user_id:
            self.approval_repository.create_if_missing(
                case_id=case_id,
                manager_user_id=case.manager_user_id,
                manager_name=case.manager_name or "Руководитель",
                status=ApprovalStatus.PENDING.value,
            )

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

    def _parse_id(self, action: str, prefix: str) -> int:
        try:
            return int(action.replace(prefix, "", 1))
        except ValueError:
            return 0

    def _substitution_list(self, role: str, user_id: str) -> MaxWebhookResponse:
        rows = self.substitution_repository.list_drafts_for_user(user_id)
        if not rows:
            text = "У тебя пока нет сохраненных черновиков замещений."
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

        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=get_menu_for_role(role),
            outbound=MaxOutboundMessage(
                text=text,
                buttons=[
                    MaxOutboundButton(title="Назначить замещение", action=BotAction.SUBSTITUTION_CREATE),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            active_flow=None,
        )

    def _send_outbound(self, inbound: MaxUpdate, outbound: MaxOutboundMessage) -> None:
        if not self.max_client.is_configured():
            return

        try:
            if inbound.update_type == "message_callback" and inbound.callback:
                self.max_client.answer_callback(
                    callback_id=inbound.callback.callback_id,
                    new_text=outbound.text,
                    buttons=outbound.buttons,
                )
                return

            if inbound.update_type == "bot_started":
                self.max_client.send_message(
                    chat_id=inbound.chat_id,
                    text=outbound.text,
                    buttons=outbound.buttons,
                )
                return

            if inbound.message:
                self.max_client.send_message(
                    chat_id=inbound.message.recipient.chat_id,
                    text=outbound.text,
                    buttons=outbound.buttons,
                )
        except Exception:
            return

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

    def _approval_status_label(self, status: str) -> str:
        labels = {
            ApprovalStatus.PENDING.value: "Ожидает",
            ApprovalStatus.APPROVED.value: "Согласовано",
            ApprovalStatus.REJECTED.value: "Отклонено",
        }
        return labels.get(status, status)
