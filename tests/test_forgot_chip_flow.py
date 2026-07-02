from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.bot.router import MaxWebhookRouter
from app.domain.dialog_state import UserDialogState
from app.domain.enums import ApprovalStatus, AttendanceCaseStatus, AttendanceCaseType, DialogFlow
from app.integrations.google_sheets.directory import GoogleSheetsEmployeeRecord


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


class _EmptyLocalDirectoryRepository:
    def get_by_user_id(self, user_id: str):
        return None

    def get_by_employee_name(self, employee_name: str):
        return None

    def get_by_manager_user_id(self, manager_user_id: str):
        return []

    def list_by_department_names(self, department_names):
        return []

    def list_recent(self, limit: int = 50):
        return []


class _FakeScheduleService:
    def resolve_planned_start(self, **kwargs):
        return "08:30"


class _FakeCaseRepository:
    def __init__(self):
        self.created_cases = []
        self.cases = {}
        self.last_id = 500

    def create_case(self, **kwargs):
        self.last_id += 1
        self.created_cases.append(kwargs)
        self.cases[self.last_id] = SimpleNamespace(id=self.last_id, **kwargs)
        return self.last_id

    def get(self, case_id: int):
        return self.cases.get(case_id)


class _FakeApprovalRepository:
    def __init__(self):
        self.created = []

    def create_if_missing(self, **kwargs):
        self.created.append(kwargs)
        return 88


class ForgotChipFlowTests(unittest.TestCase):
    def _build_router(self) -> MaxWebhookRouter:
        router = MaxWebhookRouter()
        router.case_repository = _FakeCaseRepository()
        router.approval_repository = _FakeApprovalRepository()
        router.google_schedule_service = _FakeScheduleService()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router.employee_directory_repository = _EmptyLocalDirectoryRepository()
        router.google_directory_service = _FakeDirectoryService(
            rows=[
                GoogleSheetsEmployeeRecord(
                    employee_name="Иванов Иван Иванович",
                    employee_user_id="emp-1",
                    department_name="Отдел продаж",
                    manager_name="Петров Петр Сергеевич",
                    manager_user_id="mgr-default",
                    schedule_name="Пятидневка",
                    schedule_id="GR003",
                    role="employee",
                    is_active=True,
                ),
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
        return router

    def test_start_flow_shows_manager_choices(self) -> None:
        router = self._build_router()

        response = router._start_forgot_chip_flow("employee", "emp-1")

        self.assertIn("Выбери руководителя", response.outbound.text)
        self.assertIn("Петров Петр Сергеевич", [button.title for button in response.outbound.buttons])
        self.assertIn("Смирнов Сергей Олегович", [button.title for button in response.outbound.buttons])
        self.assertEqual(response.active_flow, DialogFlow.FORGOT_CHIP.value)

    def test_start_flow_prefers_manager_id_matching_current_manager_name(self) -> None:
        router = MaxWebhookRouter()
        router.case_repository = _FakeCaseRepository()
        router.approval_repository = _FakeApprovalRepository()
        router.google_schedule_service = _FakeScheduleService()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router.google_directory_service = _FakeDirectoryService(
            rows=[
                GoogleSheetsEmployeeRecord(
                    employee_name="Кутлуев Родион Романович",
                    employee_user_id="23325864",
                    department_name="0. Руководство",
                    manager_name="Комаровский Андрей Петрович",
                    manager_user_id="12771658",
                    schedule_name="Пятидневка",
                    schedule_id="GR004",
                    role="employee",
                    is_active=True,
                ),
                GoogleSheetsEmployeeRecord(
                    employee_name="Посунько Руслан Юрьевич",
                    employee_user_id="12771658",
                    department_name="1-ОКПКиПиБ",
                    role="top_manager",
                    is_active=True,
                ),
                GoogleSheetsEmployeeRecord(
                    employee_name="Комаровский Андрей Петрович",
                    employee_user_id="6393482",
                    department_name="1-ОКПКиПиБ",
                    role="top_manager",
                    is_active=True,
                ),
            ]
        )

        response = router._start_forgot_chip_flow("employee", "23325864")

        button_map = {button.title: button.action for button in response.outbound.buttons}
        self.assertEqual(button_map["Комаровский Андрей Петрович"], "forgot_chip.manager:6393482")

    def test_valid_time_creates_case_and_sends_for_approval(self) -> None:
        router = self._build_router()
        state = UserDialogState(
            flow=DialogFlow.FORGOT_CHIP.value,
            step="choose_manager",
            data={
                "employee_name": "Иванов Иван Иванович",
                "department_name": "Отдел продаж",
                "schedule_name": "Пятидневка",
                "schedule_id": "GR003",
            },
        )

        manager_response = router._handle_forgot_chip_flow(
            "employee",
            "emp-1",
            "",
            "forgot_chip.manager:mgr-alt",
            state,
        )
        self.assertIn("Напиши время прихода", manager_response.outbound.text)
        self.assertEqual(state.step, "enter_time")
        self.assertEqual(state.data["manager_user_id"], "mgr-alt")
        self.assertEqual(state.data["manager_name"], "Смирнов Сергей Олегович")

        result = router._handle_forgot_chip_flow("employee", "emp-1", "08:42", "", state)

        self.assertIn("Заявка `Забыл чип` отправлена на согласование.", result.outbound.text)
        self.assertEqual(result.active_flow, None)
        self.assertEqual(len(router.case_repository.created_cases), 1)
        created_case = router.case_repository.created_cases[0]
        self.assertEqual(created_case["employee_user_id"], "emp-1")
        self.assertEqual(created_case["manager_user_id"], "mgr-alt")
        self.assertEqual(created_case["case_type"], AttendanceCaseType.LATE.value)
        self.assertEqual(created_case["status"], AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value)
        self.assertEqual(created_case["actual_start"], "08:42")
        self.assertEqual(created_case["planned_start"], "08:30")
        self.assertEqual(created_case["delay_minutes"], 12)
        self.assertEqual(created_case["source"], "forgot_chip")
        self.assertIn("Забыл чип", created_case["employee_reason"])

        self.assertEqual(
            router.approval_repository.created[0],
            {
                "case_id": 501,
                "manager_user_id": "mgr-alt",
                "manager_name": "Смирнов Сергей Олегович",
                "status": ApprovalStatus.PENDING.value,
            },
        )
        router.max_client.send_message.assert_called_once()

    def test_invalid_time_keeps_flow_active(self) -> None:
        router = self._build_router()
        state = UserDialogState(
            flow=DialogFlow.FORGOT_CHIP.value,
            step="enter_time",
            data={
                "employee_name": "Иванов Иван Иванович",
                "department_name": "Отдел продаж",
                "schedule_name": "Пятидневка",
                "schedule_id": "GR003",
                "manager_user_id": "mgr-default",
                "manager_name": "Петров Петр Сергеевич",
            },
        )

        result = router._handle_forgot_chip_flow("employee", "emp-1", "8:70", "", state)

        self.assertIn("Нужен формат времени", result.outbound.text)
        self.assertEqual(result.active_flow, DialogFlow.FORGOT_CHIP.value)
        self.assertEqual(router.case_repository.created_cases, [])
        router.max_client.send_message.assert_not_called()

    def test_back_from_choose_manager_returns_to_lates_section(self) -> None:
        router = self._build_router()
        state = UserDialogState(
            flow=DialogFlow.FORGOT_CHIP.value,
            step="choose_manager",
            data={
                "employee_name": "Иванов Иван Иванович",
                "department_name": "Отдел продаж",
                "schedule_name": "Пятидневка",
                "schedule_id": "GR003",
            },
        )

        result = router._handle_forgot_chip_flow("employee", "emp-1", "", "common.back", state)

        self.assertEqual(result.outbound.text, "Раздел опозданий и объяснений.")


if __name__ == "__main__":
    unittest.main()
