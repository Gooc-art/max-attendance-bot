from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List

from app.bot.actions import BotAction
from app.bot.buttons import confirm_buttons, reason_buttons
from app.domain.dialog_state import UserDialogState
from app.domain.enums import DialogFlow
from app.integrations.google_sheets.directory import GoogleSheetsDirectoryService
from app.repositories.employee_directory_repository import EmployeeDirectoryRepository
from app.repositories.substitution_repository import SubstitutionRepository
from app.schemas.max import MaxOutboundButton, MaxOutboundMessage
from app.services.dialog_state import dialog_state_store


@dataclass
class FlowResult:
    message: MaxOutboundMessage
    completed: bool = False
    created_draft_id: int | None = None
    replacement_user_id: str = ""
    target_manager: str = ""
    replacement_user: str = ""
    date_from: str = ""
    date_to: str = ""
    reason: str = ""
    scope: str = ""
    departments: str = ""


class SubstitutionFlowService:
    STEP_REPLACEMENT = "replacement_user"
    STEP_REASON = "reason"
    STEP_DATE_FROM = "date_from"
    STEP_DATE_TO = "date_to"
    STEP_DEPARTMENTS = "departments"
    STEP_CONFIRM = "confirm"
    STEP_EXTEND_DATE_TO = "extend_date_to"

    def __init__(self) -> None:
        self.substitution_repository = SubstitutionRepository()
        self.google_directory_service = GoogleSheetsDirectoryService.from_settings()
        self.employee_directory_repository = EmployeeDirectoryRepository()

    def start(self, user_id: str) -> FlowResult:
        target_record = self._resolve_directory_record(user_id)
        target_name = (
            target_record.employee_name
            if target_record is not None and getattr(target_record, "employee_name", "")
            else user_id
        )
        dialog_state_store.set(
            user_id,
            UserDialogState(
                flow=DialogFlow.SUBSTITUTION.value,
                step=self.STEP_REPLACEMENT,
                data={
                    "target_manager": target_name,
                    "target_user_id": user_id,
                },
            ),
        )
        return FlowResult(
            message=MaxOutboundMessage(
                text=(
                    "Кто будет замещать тебя на период?\n\n"
                    "Ты: {target_name}\n"
                    "Введи ФИО или MAX ID замещающего сотрудника."
                ).format(target_name=target_name),
                buttons=[MaxOutboundButton(title="Отмена", action=BotAction.CANCEL)],
            )
        )

    def start_extend(self, user_id: str, draft_id: int) -> FlowResult:
        draft = self.substitution_repository.get_draft(draft_id, created_by_user_id=user_id)
        if draft is None:
            return FlowResult(
                message=MaxOutboundMessage(
                    text="Черновик замещения не найден.",
                    buttons=[MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU)],
                ),
                completed=True,
            )

        dialog_state_store.set(
            user_id,
            UserDialogState(
                flow=DialogFlow.SUBSTITUTION.value,
                step=self.STEP_EXTEND_DATE_TO,
                data={
                    "draft_id": str(draft.id),
                    "target_manager": draft.target_manager,
                    "replacement_user": draft.replacement_user,
                    "reason": draft.reason,
                    "date_from": draft.date_from,
                    "date_to": draft.date_to,
                    "departments_json": getattr(draft, "departments_json", "[]") or "[]",
                },
            ),
        )
        return FlowResult(
            message=MaxOutboundMessage(
                text=(
                    "Продлеваем черновик #{draft_id}.\n\n"
                    "Текущие даты: {date_from} -> {date_to}\n"
                    "Введи новую дату окончания в формате YYYY-MM-DD."
                ).format(
                    draft_id=draft.id,
                    date_from=draft.date_from,
                    date_to=draft.date_to,
                ),
                buttons=[MaxOutboundButton(title="Отмена", action=BotAction.CANCEL)],
            )
        )

    def handle_input(self, user_id: str, role: str, user_text: str, action: str, state: UserDialogState) -> FlowResult:
        normalized_text = user_text.strip()
        if action == BotAction.CANCEL or normalized_text.lower() == "отмена":
            dialog_state_store.reset(user_id)
            return FlowResult(
                message=MaxOutboundMessage(
                    text="Сценарий замещения на период отменен.",
                    buttons=[MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU)],
                ),
                completed=True,
            )

        handlers = {
            self.STEP_REPLACEMENT: self._handle_replacement,
            self.STEP_REASON: self._handle_reason,
            self.STEP_DATE_FROM: self._handle_date_from,
            self.STEP_DATE_TO: self._handle_date_to,
            self.STEP_DEPARTMENTS: self._handle_departments,
            self.STEP_CONFIRM: self._handle_confirm,
            self.STEP_EXTEND_DATE_TO: self._handle_extend_date_to,
        }
        return handlers[state.step](user_id, role, normalized_text, action, state)

    def _handle_replacement(self, user_id: str, role: str, user_text: str, action: str, state: UserDialogState) -> FlowResult:
        replacement_record = self._resolve_directory_record(user_text)
        if replacement_record is None or not getattr(replacement_record, "employee_user_id", ""):
            return FlowResult(
                message=MaxOutboundMessage(
                    text=(
                        "Не нашел замещающего сотрудника.\n\n"
                        "Введи точное ФИО или MAX ID сотрудника, который будет замещать тебя."
                    ),
                    buttons=[MaxOutboundButton(title="Отмена", action=BotAction.CANCEL)],
                )
            )
        if replacement_record.employee_user_id == user_id:
            return FlowResult(
                message=MaxOutboundMessage(
                    text="Нельзя назначить замещение самому себе. Укажи другого сотрудника.",
                    buttons=[MaxOutboundButton(title="Отмена", action=BotAction.CANCEL)],
                )
            )
        state.data["replacement_user"] = replacement_record.employee_name or user_text
        state.data["replacement_user_id"] = replacement_record.employee_user_id
        state.step = self.STEP_REASON
        dialog_state_store.set(user_id, state)
        return FlowResult(
            message=MaxOutboundMessage(
                text=(
                    "Замещающий выбран: {replacement}\n\n"
                    "Укажи причину замещения."
                ).format(replacement=state.data["replacement_user"]),
                buttons=reason_buttons(),
            )
        )

    def _handle_reason(self, user_id: str, role: str, user_text: str, action: str, state: UserDialogState) -> FlowResult:
        state.data["reason"] = user_text
        state.step = self.STEP_DATE_FROM
        dialog_state_store.set(user_id, state)
        return FlowResult(
            message=MaxOutboundMessage(
                text="Укажи дату начала в формате YYYY-MM-DD.",
                buttons=[MaxOutboundButton(title="Отмена", action=BotAction.CANCEL)],
            )
        )

    def _handle_date_from(self, user_id: str, role: str, user_text: str, action: str, state: UserDialogState) -> FlowResult:
        state.data["date_from"] = user_text
        state.step = self.STEP_DATE_TO
        dialog_state_store.set(user_id, state)
        return FlowResult(
            message=MaxOutboundMessage(
                text="Укажи дату окончания в формате YYYY-MM-DD.",
                buttons=[MaxOutboundButton(title="Отмена", action=BotAction.CANCEL)],
            )
        )

    def _handle_date_to(self, user_id: str, role: str, user_text: str, action: str, state: UserDialogState) -> FlowResult:
        state.data["date_to"] = user_text
        state.step = self.STEP_DEPARTMENTS
        state.data["departments_json"] = "[]"
        dialog_state_store.set(user_id, state)
        return FlowResult(
            message=MaxOutboundMessage(
                text="Выбери отделы, которые передаются на курирование.",
                buttons=self._department_buttons(user_id, state),
            )
        )

    def _handle_departments(self, user_id: str, role: str, user_text: str, action: str, state: UserDialogState) -> FlowResult:
        selected = self._selected_departments(state)
        if action.startswith(BotAction.SUBSTITUTION_DEPARTMENT_PREFIX):
            department = action.split(BotAction.SUBSTITUTION_DEPARTMENT_PREFIX, 1)[1].strip()
            if department and department not in selected:
                selected.append(department)
            state.data["departments_json"] = json.dumps(selected, ensure_ascii=False)
            dialog_state_store.set(user_id, state)
            return FlowResult(
                message=MaxOutboundMessage(
                    text="Выбрано: {0}\n\nМожно добавить еще отдел или завершить выбор.".format(
                        ", ".join(selected) if selected else "-"
                    ),
                    buttons=self._department_buttons(user_id, state),
                )
            )

        if action == BotAction.SUBSTITUTION_DEPARTMENTS_DONE:
            if not selected:
                return FlowResult(
                    message=MaxOutboundMessage(
                        text="Выбери хотя бы один отдел для курирования.",
                        buttons=self._department_buttons(user_id, state),
                    )
                )
            state.step = self.STEP_CONFIRM
            dialog_state_store.set(user_id, state)
            summary = self._build_summary(state.data)
            return FlowResult(
                message=MaxOutboundMessage(
                    text="Проверь данные замещения:\n\n{summary}".format(summary=summary),
                    buttons=confirm_buttons(),
                )
            )

        typed = [part.strip() for part in user_text.split(",") if part.strip()]
        for department in typed:
            if department not in selected:
                selected.append(department)
        if not selected:
            return FlowResult(
                message=MaxOutboundMessage(
                    text="Выбери отдел кнопкой или напиши один/несколько отделов через запятую.",
                    buttons=self._department_buttons(user_id, state),
                )
            )
        state.data["departments_json"] = json.dumps(selected, ensure_ascii=False)
        state.step = self.STEP_CONFIRM
        dialog_state_store.set(user_id, state)
        summary = self._build_summary(state.data)
        return FlowResult(
            message=MaxOutboundMessage(
                text="Проверь данные замещения:\n\n{summary}".format(summary=summary),
                buttons=confirm_buttons(),
            )
        )

    def _handle_confirm(self, user_id: str, role: str, user_text: str, action: str, state: UserDialogState) -> FlowResult:
        if action != BotAction.CONFIRM and user_text.lower() != "подтвердить":
            return FlowResult(
                message=MaxOutboundMessage(
                    text="Для завершения нажми `Подтвердить` или `Отмена`.",
                    buttons=confirm_buttons(),
                )
            )

        summary = self._build_summary(state.data)
        draft_id = 0
        if state.step == self.STEP_CONFIRM and state.data.get("draft_id"):
            draft_id = int(state.data["draft_id"])
            updated = self.substitution_repository.extend_draft(
                draft_id=draft_id,
                created_by_user_id=user_id,
                new_date_to=state.data.get("date_to", ""),
            )
            if updated is None:
                return FlowResult(
                    message=MaxOutboundMessage(
                        text="Черновик для продления не найден.",
                        buttons=[MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU)],
                    ),
                    completed=True,
                )
        else:
            draft_id = self.substitution_repository.create_draft(
                created_by_user_id=user_id,
                role=role,
                data=state.data,
            )
        dialog_state_store.reset(user_id)
        return FlowResult(
            message=MaxOutboundMessage(
                text=(
                    "Запрос на замещение на период #{draft_id} отправлен замещающему на согласование.\n\n"
                    "{summary}"
                ).format(
                    draft_id=draft_id,
                    summary=summary,
                ),
                buttons=[
                    MaxOutboundButton(title="Мои замещения", action=BotAction.SUBSTITUTION_LIST),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            completed=True,
            created_draft_id=draft_id,
            replacement_user_id=state.data.get("replacement_user_id", ""),
            target_manager=state.data.get("target_manager", ""),
            replacement_user=state.data.get("replacement_user", ""),
            date_from=state.data.get("date_from", ""),
            date_to=state.data.get("date_to", ""),
            reason=state.data.get("reason", ""),
            scope=state.data.get("scope", ""),
            departments=state.data.get("departments_json", "[]"),
        )

    def _handle_extend_date_to(self, user_id: str, role: str, user_text: str, action: str, state: UserDialogState) -> FlowResult:
        state.data["date_to"] = user_text
        state.step = self.STEP_CONFIRM
        dialog_state_store.set(user_id, state)
        summary = self._build_summary(state.data)
        return FlowResult(
            message=MaxOutboundMessage(
                text="Проверь новое окончание замещения:\n\n{summary}".format(summary=summary),
                buttons=confirm_buttons(),
            )
        )

    def _build_summary(self, data: Dict[str, str]) -> str:
        departments = self._departments_label(data.get("departments_json", "[]"))
        lines: List[str] = [
            "Кого замещают: {0}".format(data.get("target_manager", "-")),
            "Кто замещает: {0}".format(data.get("replacement_user", "-")),
            "Причина: {0}".format(data.get("reason", "-")),
            "Период: {0} -> {1}".format(data.get("date_from", "-"), data.get("date_to", "-")),
            "Курируемые отделы: {0}".format(departments),
        ]
        return "\n".join(lines)

    def _selected_departments(self, state: UserDialogState) -> List[str]:
        raw = state.data.get("departments_json", "[]")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def _departments_label(self, raw: str) -> str:
        try:
            value = json.loads(raw or "[]")
        except json.JSONDecodeError:
            value = []
        if not isinstance(value, list) or not value:
            return "-"
        return ", ".join(str(item).strip() for item in value if str(item).strip()) or "-"

    def _department_buttons(self, user_id: str, state: UserDialogState) -> List[MaxOutboundButton]:
        departments = self._available_departments(user_id, state)
        selected = set(self._selected_departments(state))
        buttons: List[MaxOutboundButton] = []
        for index, department in enumerate(departments[:8]):
            marker = "✓ " if department in selected else ""
            buttons.append(
                MaxOutboundButton(
                    title=f"{marker}{department}",
                    action=f"{BotAction.SUBSTITUTION_DEPARTMENT_PREFIX}{department}",
                    emoji="🏢",
                    row=index,
                )
            )
        buttons.append(MaxOutboundButton(title="Готово", action=BotAction.SUBSTITUTION_DEPARTMENTS_DONE, emoji="✅", row=9))
        buttons.append(MaxOutboundButton(title="Отмена", action=BotAction.CANCEL, emoji="✖️", row=9))
        return buttons

    def _available_departments(self, user_id: str, state: UserDialogState) -> List[str]:
        departments: List[str] = []
        seen: set[str] = set()

        def add(value: str) -> None:
            department = str(value or "").strip()
            if department and department not in seen:
                seen.add(department)
                departments.append(department)

        target_record = self._resolve_directory_record(state.data.get("target_user_id", user_id))
        if target_record is not None:
            add(getattr(target_record, "department_name", ""))

        for row in self.google_directory_service.list_employees():
            if not getattr(row, "is_active", True):
                continue
            if getattr(row, "manager_user_id", "") == state.data.get("target_user_id", user_id):
                add(getattr(row, "department_name", ""))
        for row in self.employee_directory_repository.list_recent(limit=500):
            if not getattr(row, "is_active", True):
                continue
            if getattr(row, "manager_user_id", "") == state.data.get("target_user_id", user_id):
                add(getattr(row, "department_name", ""))

        return departments or ["Все отделы"]

    def _resolve_directory_record(self, value: str):
        normalized = str(value or "").strip()
        if not normalized:
            return None
        google_record = self.google_directory_service.get_by_user_id(normalized)
        if google_record is not None:
            return google_record
        google_record = self.google_directory_service.get_by_employee_name(normalized)
        if google_record is not None:
            return google_record
        local_record = self.employee_directory_repository.get_by_user_id(normalized)
        if local_record is not None:
            return local_record
        return self.employee_directory_repository.get_by_employee_name(normalized)
