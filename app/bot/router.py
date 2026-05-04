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
from app.repositories.approval_repository import ApprovalRepository
from app.repositories.attendance_case_repository import AttendanceCaseRepository
from app.repositories.skud_import_repository import SkudImportRepository
from app.repositories.substitution_repository import SubstitutionRepository
from app.repositories.user_role_override_repository import UserRoleOverrideRepository
from app.schemas.max import MaxOutboundButton, MaxOutboundMessage, MaxUpdate, MaxWebhookResponse
from app.services.demo_data import ensure_demo_approvals_for_manager, ensure_demo_cases_for_employee
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
            if target_role == Role.MANAGER.value:
                ensure_demo_approvals_for_manager(event["user_id"])
            if target_role == Role.EMPLOYEE.value:
                ensure_demo_cases_for_employee(event["user_id"])
            response = self._menu_response(target_role, "Роль переключена на: {0}".format(target_role))
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

        if action == BotAction.MENU_SECURITY_IMPORT or user_text == "Загрузить выгрузку СКУД":
            response = self._security_import_help(role, event["user_id"])
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.MENU_IMPORT_HISTORY or user_text == "История импортов":
            response = self._security_import_history(role)
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
            response = self._stub_section(role, "Раздел отмены замещения подготовлен как следующий шаг.")
            self._send_outbound(payload, response.outbound)
            return response

        if action == BotAction.SUBSTITUTION_EXTEND:
            response = self._stub_section(role, "Раздел продления замещения подготовлен как следующий шаг.")
            self._send_outbound(payload, response.outbound)
            return response

        if action in {BotAction.APPROVALS_NEW, BotAction.APPROVALS_IN_PROGRESS, BotAction.APPROVALS_OVERDUE, BotAction.APPROVALS_HISTORY}:
            response = self._approvals_list(role, event["user_id"])
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
            response = self._stub_section(
                role,
                "Генерация отчетов будет подключена следующим этапом. Выбрано: {0}.".format(user_text or action),
            )
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
        return MaxWebhookResponse(
            ok=True,
            role=role,
            menu=menu,
            outbound=MaxOutboundMessage(text=text, buttons=main_menu_buttons(role)),
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
            ensure_demo_cases_for_employee(user_id)
            rows = self.case_repository.list_for_employee_user(user_id)

        if not rows:
            text = "У тебя пока нет зарегистрированных случаев."
            buttons = [MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU)]
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

    def _approvals_list(self, role: str, user_id: str, prefix_text: str = "") -> MaxWebhookResponse:
        rows = self.approval_repository.list_pending_for_manager(user_id)
        if not rows:
            text = prefix_text + "У тебя нет согласований в статусе ожидания."
            buttons = [MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU)]
        else:
            lines = []
            buttons = []
            for approval, case in rows[:8]:
                lines.append(
                    "#{approval_id} | {employee} | {date} | {kind}".format(
                        approval_id=approval.id,
                        employee=case.employee_name,
                        date=case.event_date,
                        kind="Опоздание" if case.case_type == "late" else "Неявка",
                    )
                )
                buttons.append(
                    MaxOutboundButton(
                        title="Открыть #{0}".format(approval.id),
                        action="{0}{1}".format(BotAction.APPROVAL_OPEN_PREFIX, approval.id),
                    )
                )
            buttons.append(MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU))
            text = prefix_text + "Согласования в ожидании:\n\n{lines}".format(lines="\n".join(lines))

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
