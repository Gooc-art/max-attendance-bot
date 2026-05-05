from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.bot.actions import BotAction
from app.bot.router import MaxWebhookRouter
from app.domain.dialog_state import UserDialogState
from app.domain.enums import DialogFlow


class _FakeDraft:
    def __init__(self, draft_id: int = 1):
        self.id = draft_id
        self.created_by_user_id = "mgr-1"
        self.role = "manager"
        self.target_manager = "Петров Петр Сергеевич"
        self.replacement_user = "Волков Игорь Павлович"
        self.reason = "Отпуск"
        self.date_from = "2026-07-01"
        self.date_to = "2026-07-14"
        self.scope = "both"
        self.status = "draft"


class _FakeSubstitutionRepository:
    def __init__(self):
        self.drafts = [_FakeDraft()]
        self.cancelled = []
        self.extended = []

    def list_drafts_for_user(self, created_by_user_id: str):
        return list(self.drafts)

    def get_draft(self, draft_id: int, created_by_user_id: str | None = None):
        for draft in self.drafts:
            if draft.id == draft_id and (created_by_user_id is None or draft.created_by_user_id == created_by_user_id):
                return draft
        return None

    def cancel_draft(self, draft_id: int, created_by_user_id: str):
        draft = self.get_draft(draft_id, created_by_user_id)
        if draft is None:
            return None
        draft.status = "cancelled"
        self.cancelled.append(draft_id)
        return draft

    def extend_draft(self, draft_id: int, created_by_user_id: str, new_date_to: str):
        draft = self.get_draft(draft_id, created_by_user_id)
        if draft is None:
            return None
        draft.date_to = new_date_to
        draft.status = "draft"
        self.extended.append((draft_id, new_date_to))
        return draft


class _FakeCaseRepository:
    def __init__(self):
        self.case = SimpleNamespace(
            id=101,
            employee_user_id="emp-1",
            employee_name="Иванов Иван Иванович",
            department_name="Отдел продаж",
            manager_user_id="mgr-default",
            manager_name="Петров Петр Сергеевич",
            case_type="late",
            event_date="2026-05-05",
            planned_start="08:30",
            actual_start="08:44",
            delay_minutes=14,
            employee_reason="",
            status="awaiting_employee_reason",
        )

    def get(self, case_id: int):
        if case_id == self.case.id:
            return self.case
        return None


class SubstitutionCrudTests(unittest.TestCase):
    def test_substitution_list_shows_actions_for_each_draft(self) -> None:
        router = MaxWebhookRouter()
        router.substitution_repository = _FakeSubstitutionRepository()

        response = router._substitution_list("manager", "mgr-1")

        actions = [button.action for button in response.outbound.buttons]
        self.assertIn(f"{BotAction.SUBSTITUTION_CANCEL_PREFIX}1", actions)
        self.assertIn(f"{BotAction.SUBSTITUTION_EXTEND_PREFIX}1", actions)

    def test_substitution_cancel_changes_status(self) -> None:
        router = MaxWebhookRouter()
        repo = _FakeSubstitutionRepository()
        router.substitution_repository = repo

        response = router._cancel_substitution_draft("manager", "mgr-1", 1)

        self.assertEqual(repo.drafts[0].status, "cancelled")
        self.assertIn("Черновик #1 отменен.", response.outbound.text)

    def test_substitution_extend_updates_date_to_via_flow(self) -> None:
        router = MaxWebhookRouter()
        repo = _FakeSubstitutionRepository()
        router.substitution_repository = repo
        router.substitution_flow.substitution_repository = repo

        start = router._start_substitution_extend_flow("manager", "mgr-1", 1)
        self.assertIn("Продлеваем черновик #1.", start.outbound.text)

        state = UserDialogState(
            flow=DialogFlow.SUBSTITUTION.value,
            step="extend_date_to",
            data={
                "draft_id": "1",
                "target_manager": "Петров Петр Сергеевич",
                "replacement_user": "Волков Игорь Павлович",
                "reason": "Отпуск",
                "date_from": "2026-07-01",
                "date_to": "2026-07-14",
                "scope": "both",
            },
        )

        result = router.substitution_flow.handle_input("mgr-1", "manager", "2026-07-21", "", state)
        self.assertIn("Проверь новое окончание замещения", result.message.text)

        confirm = router.substitution_flow.handle_input("mgr-1", "manager", "", BotAction.CONFIRM, state)

        self.assertTrue(confirm.completed)
        self.assertEqual(repo.extended[-1], (1, "2026-07-21"))
        self.assertEqual(repo.drafts[0].date_to, "2026-07-21")


if __name__ == "__main__":
    unittest.main()
