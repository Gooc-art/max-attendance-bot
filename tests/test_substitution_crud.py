from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

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
        self.target_user_id = "mgr-1"
        self.replacement_user = "Волков Игорь Павлович"
        self.replacement_user_id = "emp-2"
        self.reason = "Отпуск"
        self.date_from = "2026-07-01"
        self.date_to = "2026-07-14"
        self.scope = "both"
        self.departments_json = '["Отдел продаж"]'
        self.status = "pending_replacement_approval"


class _FakeSubstitutionRepository:
    def __init__(self):
        self.drafts = [_FakeDraft()]
        self.cancelled = []
        self.extended = []
        self.approved = []
        self.rejected = []
        self.created = []

    def create_draft(self, created_by_user_id: str, role: str, data):
        draft = _FakeDraft(draft_id=2)
        draft.created_by_user_id = created_by_user_id
        draft.role = role
        draft.target_manager = data.get("target_manager", "")
        draft.target_user_id = data.get("target_user_id", "")
        draft.replacement_user = data.get("replacement_user", "")
        draft.replacement_user_id = data.get("replacement_user_id", "")
        draft.reason = data.get("reason", "")
        draft.date_from = data.get("date_from", "")
        draft.date_to = data.get("date_to", "")
        draft.departments_json = data.get("departments_json", "[]")
        self.drafts.append(draft)
        self.created.append(data)
        return draft.id

    def list_drafts_for_user(self, created_by_user_id: str):
        return list(self.drafts)

    def list_approved_overlapping(self, date_from: str, date_to: str):
        return [draft for draft in self.drafts if draft.status == "approved"]

    @staticmethod
    def departments_for_draft(draft):
        return ["Отдел продаж"] if getattr(draft, "departments_json", "") else []

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
        draft.status = "pending_replacement_approval"
        self.extended.append((draft_id, new_date_to))
        return draft

    def get_draft_for_replacement(self, draft_id: int, replacement_user_id: str):
        draft = self.get_draft(draft_id)
        if draft is None or draft.replacement_user_id != replacement_user_id:
            return None
        return draft

    def approve_draft(self, draft_id: int, replacement_user_id: str):
        draft = self.get_draft_for_replacement(draft_id, replacement_user_id)
        if draft is None:
            return None
        draft.status = "approved"
        self.approved.append(draft_id)
        return draft

    def reject_draft(self, draft_id: int, replacement_user_id: str):
        draft = self.get_draft_for_replacement(draft_id, replacement_user_id)
        if draft is None:
            return None
        draft.status = "rejected"
        self.rejected.append(draft_id)
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
        self.assertIn("Замещение #1 снято.", response.outbound.text)

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
                "departments_json": '["Отдел продаж"]',
            },
        )

        result = router.substitution_flow.handle_input("mgr-1", "manager", "2026-07-21", "", state)
        self.assertIn("Проверь новое окончание замещения", result.message.text)

        confirm = router.substitution_flow.handle_input("mgr-1", "manager", "", BotAction.CONFIRM, state)

        self.assertTrue(confirm.completed)
        self.assertEqual(repo.extended[-1], (1, "2026-07-21"))
        self.assertEqual(repo.drafts[0].date_to, "2026-07-21")

    def test_substitution_flow_selects_departments_instead_of_scope(self) -> None:
        router = MaxWebhookRouter()
        repo = _FakeSubstitutionRepository()
        router.substitution_flow.substitution_repository = repo
        router.substitution_flow.google_directory_service = SimpleNamespace(
            get_by_user_id=lambda user_id: SimpleNamespace(
                employee_name="Петров Петр Сергеевич",
                employee_user_id="mgr-1",
                department_name="Отдел продаж",
            )
            if user_id == "mgr-1"
            else SimpleNamespace(
                employee_name="Волков Игорь Павлович",
                employee_user_id="emp-2",
                department_name="Склад",
            )
            if user_id == "emp-2"
            else None,
            get_by_employee_name=lambda name: SimpleNamespace(
                employee_name="Волков Игорь Павлович",
                employee_user_id="emp-2",
                department_name="Склад",
            )
            if name == "Волков Игорь Павлович"
            else None,
            list_employees=lambda: [
                SimpleNamespace(
                    employee_name="Иванов Иван Иванович",
                    employee_user_id="emp-1",
                    manager_user_id="mgr-1",
                    department_name="Отдел продаж",
                    is_active=True,
                ),
                SimpleNamespace(
                    employee_name="Сидоров Сидор Сидорович",
                    employee_user_id="emp-3",
                    manager_user_id="mgr-1",
                    department_name="Отдел сервиса",
                    is_active=True,
                ),
            ],
        )
        router.substitution_flow.employee_directory_repository = SimpleNamespace(
            get_by_user_id=lambda user_id: None,
            get_by_employee_name=lambda name: None,
            list_recent=lambda limit=500: [],
        )

        state = UserDialogState(
            flow=DialogFlow.SUBSTITUTION.value,
            step="replacement_user",
            data={
                "target_manager": "Петров Петр Сергеевич",
                "target_user_id": "mgr-1",
            },
        )

        replacement = router.substitution_flow.handle_input("mgr-1", "manager", "Волков Игорь Павлович", "", state)
        self.assertIn("Укажи причину", replacement.message.text)

        router.substitution_flow.handle_input("mgr-1", "manager", "Отпуск", "", state)
        router.substitution_flow.handle_input("mgr-1", "manager", "2026-07-01", "", state)
        date_to = router.substitution_flow.handle_input("mgr-1", "manager", "2026-07-14", "", state)
        self.assertIn("Выбери отделы", date_to.message.text)
        self.assertTrue(any(button.title.endswith("Отдел продаж") for button in date_to.message.buttons))

        department = router.substitution_flow.handle_input(
            "mgr-1",
            "manager",
            "",
            f"{BotAction.SUBSTITUTION_DEPARTMENT_PREFIX}Отдел продаж",
            state,
        )
        self.assertIn("Выбрано: Отдел продаж", department.message.text)

        done = router.substitution_flow.handle_input(
            "mgr-1",
            "manager",
            "",
            BotAction.SUBSTITUTION_DEPARTMENTS_DONE,
            state,
        )
        self.assertIn("Курируемые отделы: Отдел продаж", done.message.text)

        confirm = router.substitution_flow.handle_input("mgr-1", "manager", "", BotAction.CONFIRM, state)
        self.assertTrue(confirm.completed)
        self.assertEqual(repo.created[-1]["departments_json"], '["Отдел продаж"]')

    def test_substitution_list_shows_replacement_approval_status(self) -> None:
        router = MaxWebhookRouter()
        router.substitution_repository = _FakeSubstitutionRepository()

        response = router._substitution_list("manager", "mgr-1")

        self.assertIn("Ожидает согласования замещающего", response.outbound.text)

    def test_replacement_can_approve_substitution(self) -> None:
        router = MaxWebhookRouter()
        repo = _FakeSubstitutionRepository()
        router.substitution_repository = repo
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True

        response = router._approve_substitution_draft("employee", "emp-2", 1)

        self.assertEqual(repo.drafts[0].status, "approved")
        self.assertIn("согласовал замещение #1", response.outbound.text.lower())

    def test_replacement_can_reject_substitution(self) -> None:
        router = MaxWebhookRouter()
        repo = _FakeSubstitutionRepository()
        router.substitution_repository = repo
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True

        response = router._reject_substitution_draft("employee", "emp-2", 1)

        self.assertEqual(repo.drafts[0].status, "rejected")
        self.assertIn("отклонил замещение #1", response.outbound.text.lower())

    def test_curated_department_cases_are_visible_to_replacement(self) -> None:
        router = MaxWebhookRouter()
        substitution_repo = _FakeSubstitutionRepository()
        substitution_repo.drafts[0].status = "approved"
        router.substitution_repository = substitution_repo
        direct_case = SimpleNamespace(id=1, status="awaiting_manager_approval")
        curated_case = SimpleNamespace(id=2, status="awaiting_manager_approval")
        router.case_repository = SimpleNamespace(
            list_for_manager_user=lambda user_id, limit=500: [direct_case],
            list_for_department_names=lambda departments, statuses=None, limit=500: [curated_case]
            if departments == ["Отдел продаж"]
            else [],
        )

        rows = router._manager_case_rows("emp-2", statuses=["awaiting_manager_approval"], limit=20)

        self.assertEqual([row.id for row in rows], [1, 2])


if __name__ == "__main__":
    unittest.main()
