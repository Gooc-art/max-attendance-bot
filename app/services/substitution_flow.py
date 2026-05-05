from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from app.bot.actions import BotAction
from app.bot.buttons import confirm_buttons, reason_buttons, scope_buttons
from app.domain.dialog_state import UserDialogState
from app.domain.enums import DialogFlow
from app.repositories.substitution_repository import SubstitutionRepository
from app.schemas.max import MaxOutboundButton, MaxOutboundMessage
from app.services.dialog_state import dialog_state_store


@dataclass
class FlowResult:
    message: MaxOutboundMessage
    completed: bool = False


class SubstitutionFlowService:
    STEP_TARGET = "target_manager"
    STEP_REPLACEMENT = "replacement_user"
    STEP_REASON = "reason"
    STEP_DATE_FROM = "date_from"
    STEP_DATE_TO = "date_to"
    STEP_SCOPE = "scope"
    STEP_CONFIRM = "confirm"
    STEP_EXTEND_DATE_TO = "extend_date_to"

    def __init__(self) -> None:
        self.substitution_repository = SubstitutionRepository()

    def start(self, user_id: str) -> FlowResult:
        dialog_state_store.set(
            user_id,
            UserDialogState(
                flow=DialogFlow.SUBSTITUTION.value,
                step=self.STEP_TARGET,
                data={},
            ),
        )
        return FlowResult(
            message=MaxOutboundMessage(
                text="Кого замещаем? Введи ФИО или ID основного руководителя.",
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
                    "scope": draft.scope,
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
                    text="Сценарий замещения отменен.",
                    buttons=[MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU)],
                ),
                completed=True,
            )

        handlers = {
            self.STEP_TARGET: self._handle_target,
            self.STEP_REPLACEMENT: self._handle_replacement,
            self.STEP_REASON: self._handle_reason,
            self.STEP_DATE_FROM: self._handle_date_from,
            self.STEP_DATE_TO: self._handle_date_to,
            self.STEP_SCOPE: self._handle_scope,
            self.STEP_CONFIRM: self._handle_confirm,
            self.STEP_EXTEND_DATE_TO: self._handle_extend_date_to,
        }
        return handlers[state.step](user_id, role, normalized_text, action, state)

    def _handle_target(self, user_id: str, role: str, user_text: str, action: str, state: UserDialogState) -> FlowResult:
        state.data["target_manager"] = user_text
        state.step = self.STEP_REPLACEMENT
        dialog_state_store.set(user_id, state)
        return FlowResult(
            message=MaxOutboundMessage(
                text="Кто будет замещать? Введи ФИО или ID замещающего сотрудника.",
                buttons=[MaxOutboundButton(title="Отмена", action=BotAction.CANCEL)],
            )
        )

    def _handle_replacement(self, user_id: str, role: str, user_text: str, action: str, state: UserDialogState) -> FlowResult:
        state.data["replacement_user"] = user_text
        state.step = self.STEP_REASON
        dialog_state_store.set(user_id, state)
        return FlowResult(
            message=MaxOutboundMessage(
                text="Укажи причину замещения.",
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
        state.step = self.STEP_SCOPE
        dialog_state_store.set(user_id, state)
        return FlowResult(
            message=MaxOutboundMessage(
                text="Что передается замещающему?",
                buttons=scope_buttons(),
            )
        )

    def _handle_scope(self, user_id: str, role: str, user_text: str, action: str, state: UserDialogState) -> FlowResult:
        state.data["scope"] = user_text
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
                text="Замещение зафиксировано как черновик #{draft_id}.\n\n{summary}".format(
                    draft_id=draft_id,
                    summary=summary,
                ),
                buttons=[
                    MaxOutboundButton(title="Мои замещения", action=BotAction.SUBSTITUTION_LIST),
                    MaxOutboundButton(title="Главное меню", action=BotAction.MAIN_MENU),
                ],
            ),
            completed=True,
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
        lines: List[str] = [
            "Кого замещаем: {0}".format(data.get("target_manager", "-")),
            "Кто замещает: {0}".format(data.get("replacement_user", "-")),
            "Причина: {0}".format(data.get("reason", "-")),
            "Период: {0} -> {1}".format(data.get("date_from", "-"), data.get("date_to", "-")),
            "Полномочия: {0}".format(data.get("scope", "-")),
        ]
        return "\n".join(lines)
