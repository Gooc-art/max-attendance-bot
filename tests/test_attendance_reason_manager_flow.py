from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.bot.actions import BotAction
from app.bot.router import MaxWebhookRouter
from app.domain.dialog_state import UserDialogState
from app.domain.enums import ApprovalStatus, AttendanceCaseStatus, DialogFlow
from app.integrations.google_sheets.directory import GoogleSheetsEmployeeRecord
from app.services.dialog_state import dialog_state_store


class _FakeDirectoryService:
    def __init__(self, rows=None):
        self.rows = rows or []

    def list_employees(self, refresh: bool = False):
        return list(self.rows)

    def get_by_user_id(self, user_id: str, refresh: bool = False):
        for row in self.rows:
            if row.employee_user_id == user_id:
                return row
        return None


class _FakeCaseRepository:
    def __init__(self, case=None):
        self.updated_managers = []
        self.updated_reasons = []
        self.case = case or SimpleNamespace(
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
            status=AttendanceCaseStatus.AWAITING_EMPLOYEE_REASON.value,
            source="manual",
        )

    def get(self, case_id: int):
        if case_id == self.case.id:
            return self.case
        return None

    def update_manager(self, case_id: int, manager_user_id: str, manager_name: str):
        self.updated_managers.append((case_id, manager_user_id, manager_name))
        self.case.manager_user_id = manager_user_id
        self.case.manager_name = manager_name
        return self.case

    def update_reason_and_status(self, case_id: int, employee_reason: str, status: str):
        self.updated_reasons.append((case_id, employee_reason, status))
        self.case.employee_reason = employee_reason
        self.case.status = status
        return self.case


class _FakeApprovalRepository:
    def __init__(self):
        self.created = []

    def create_if_missing(self, **kwargs):
        self.created.append(kwargs)
        return 77


class AttendanceReasonManagerFlowTests(unittest.TestCase):
    def test_case_card_prompts_for_manager_selection_first(self) -> None:
        router = MaxWebhookRouter()
        router.case_repository = _FakeCaseRepository()

        response = router._employee_case_card("employee", "emp-1", 101)

        self.assertIn("Объяснить", [button.title for button in response.outbound.buttons])
        self.assertTrue(
            any(button.action.startswith(BotAction.EMPLOYEE_REASON_START_PREFIX) for button in response.outbound.buttons)
        )

    def test_reason_flow_uses_selected_manager_before_sending_reason(self) -> None:
        router = MaxWebhookRouter()
        router.case_repository = _FakeCaseRepository()
        router.approval_repository = _FakeApprovalRepository()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router.google_directory_service = _FakeDirectoryService(
            rows=[
                GoogleSheetsEmployeeRecord(
                    employee_name="Петров Петр Сергеевич",
                    employee_user_id="mgr-default",
                    department_name="Отдел продаж",
                    role="manager",
                    is_active=True,
                ),
                GoogleSheetsEmployeeRecord(
                    employee_name="Смирнов Сергей Олегович",
                    employee_user_id="mgr-alt",
                    department_name="Отдел продаж",
                    role="manager",
                    is_active=True,
                ),
            ]
        )

        start_response = router._start_attendance_reason_flow("employee", "emp-1", 101)
        self.assertIn("Выбери руководителя", start_response.outbound.text)
        self.assertIn("Смирнов Сергей Олегович", [button.title for button in start_response.outbound.buttons])

        state = UserDialogState(
            flow=DialogFlow.ATTENDANCE_REASON.value,
            step="choose_manager",
            data={"case_id": "101"},
        )
        manager_response = router._handle_attendance_reason_flow(
            "employee",
            "emp-1",
            "",
            "employee.manager:101:mgr-alt",
            state,
        )
        self.assertIn("Теперь выбери причину", manager_response.outbound.text)
        self.assertEqual(router.case_repository.updated_managers[-1], (101, "mgr-alt", "Смирнов Сергей Олегович"))
        self.assertEqual(state.step, "choose_reason")
        self.assertEqual(state.data["manager_user_id"], "mgr-alt")

        reason_response = router._handle_attendance_reason_flow(
            "employee",
            "emp-1",
            "",
            "employee.reason:101:personal_reason",
            state,
        )
        self.assertIn("Причина по случаю #101 сохранена: Личная причина.", reason_response.outbound.text)
        self.assertEqual(router.approval_repository.created[0]["manager_user_id"], "mgr-alt")
        router.max_client.send_message.assert_called_once()
        self.assertEqual(router.case_repository.updated_reasons[-1], (101, "Личная причина", AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value))

    def test_absence_case_card_shows_return_early_button(self) -> None:
        case = SimpleNamespace(
            id=101,
            employee_user_id="emp-1",
            employee_name="Иванов Иван Иванович",
            department_name="Отдел продаж",
            manager_user_id="mgr-default",
            manager_name="Петров Петр Сергеевич",
            case_type="absent",
            event_date="2026-05-21",
            planned_start="08:30",
            actual_start="",
            delay_minutes=0,
            employee_reason="Отпуск. Период: 2026-05-21 - 2026-05-25",
            status=AttendanceCaseStatus.JUSTIFIED.value,
            source="attendance_notice",
        )
        router = MaxWebhookRouter()
        router.case_repository = _FakeCaseRepository(case)

        response = router._employee_case_card("employee", "emp-1", 101)

        self.assertIn("Период: 2026-05-21 - 2026-05-25", response.outbound.text)
        self.assertIn("Выйду раньше", [button.title for button in response.outbound.buttons])

    def test_absence_period_edit_updates_case_and_reopens_approval(self) -> None:
        dialog_state_store.reset("emp-1")
        case = SimpleNamespace(
            id=101,
            employee_user_id="emp-1",
            employee_name="Иванов Иван Иванович",
            department_name="Отдел продаж",
            manager_user_id="mgr-default",
            manager_name="Петров Петр Сергеевич",
            case_type="absent",
            event_date="2026-05-21",
            planned_start="08:30",
            actual_start="",
            delay_minutes=0,
            employee_reason="Отпуск. Период: 2026-05-21 - 2026-05-25",
            status=AttendanceCaseStatus.JUSTIFIED.value,
            source="attendance_notice",
        )
        router = MaxWebhookRouter()
        router.case_repository = _FakeCaseRepository(case)
        router.approval_repository = _FakeApprovalRepository()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True

        start_response = router._start_absence_period_edit_flow("employee", "emp-1", 101)
        self.assertIn("Напиши новую дату окончания", start_response.outbound.text)

        state = UserDialogState(
            flow=DialogFlow.ABSENCE_PERIOD_EDIT.value,
            step="enter_date_to",
            data={
                "case_id": "101",
                "date_from": "2026-05-21",
                "date_to": "2026-05-25",
                "reason_label": "Отпуск",
            },
        )

        result = router._handle_absence_period_edit_flow("employee", "emp-1", "2026-05-23", "", state)

        self.assertIn("Дата окончания обновлена.", result.outbound.text)
        self.assertEqual(
            router.case_repository.updated_reasons[-1],
            (
                101,
                "Отпуск. Период: 2026-05-21 - 2026-05-23",
                AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value,
            ),
        )
        self.assertEqual(
            router.approval_repository.created[-1],
            {
                "case_id": 101,
                "manager_user_id": "mgr-default",
                "manager_name": "Петров Петр Сергеевич",
                "status": ApprovalStatus.PENDING.value,
            },
        )
        router.max_client.send_message.assert_called_once()
        dialog_state_store.reset("emp-1")


if __name__ == "__main__":
    unittest.main()
