from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from threading import Event
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

    def get_by_employee_name(self, employee_name: str, refresh: bool = False):
        for row in self.rows:
            if row.employee_name == employee_name:
                return row
        return None


class _RefreshOnMissDirectoryService(_FakeDirectoryService):
    def __init__(self, rows=None):
        super().__init__(rows=rows)
        self.refresh_calls = []

    def get_by_user_id(self, user_id: str, refresh: bool = False):
        self.refresh_calls.append(refresh)
        if not refresh:
            return None
        return super().get_by_user_id(user_id, refresh=refresh)


class _FakeScheduleService:
    def resolve_planned_start(self, **kwargs):
        return "08:30"


class _FakeCaseRepository:
    def __init__(self):
        self.created_cases = []
        self.cases = {}
        self.last_id = 800

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
        return 99


class _FakeSubstitutionRepository:
    def __init__(self, drafts=None):
        self.drafts = drafts or []

    def list_approved_overlapping(self, date_from: str, date_to: str):
        return [
            draft
            for draft in self.drafts
            if draft.status == "approved" and draft.date_from <= date_to and draft.date_to >= date_from
        ]

    @staticmethod
    def departments_for_draft(draft):
        return list(getattr(draft, "departments", []))


class _LocalDirectoryRepository:
    def __init__(self, rows):
        self.rows = rows
        self.list_recent_calls = 0
        self.get_by_employee_name_calls = 0

    def get_by_user_id(self, user_id: str):
        for row in self.rows:
            if getattr(row, "employee_user_id", "") == user_id:
                return row
        return None

    def get_by_employee_name(self, employee_name: str):
        self.get_by_employee_name_calls += 1
        for row in self.rows:
            if getattr(row, "employee_name", "") == employee_name:
                return row
        return None

    def get_by_manager_user_id(self, manager_user_id: str):
        return [
            row
            for row in self.rows
            if getattr(row, "manager_user_id", "") == manager_user_id and getattr(row, "is_active", True)
        ]

    def list_by_department_names(self, department_names):
        departments = set(department_names)
        return [
            row
            for row in self.rows
            if getattr(row, "department_name", "") in departments and getattr(row, "is_active", True)
        ]

    def list_recent(self, limit: int = 50):
        self.list_recent_calls += 1
        return list(self.rows)[:limit]


class RunningLateFlowTests(unittest.TestCase):
    def _build_router(self) -> MaxWebhookRouter:
        router = MaxWebhookRouter()
        router.case_repository = _FakeCaseRepository()
        router.approval_repository = _FakeApprovalRepository()
        router.google_schedule_service = _FakeScheduleService()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router.employee_directory_repository = _LocalDirectoryRepository([])
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
                    manager_name="Орлов Олег Олегович",
                    manager_user_id="top-1",
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
                GoogleSheetsEmployeeRecord(
                    employee_name="Орлов Олег Олегович",
                    employee_user_id="top-1",
                    department_name="Топ-руководство",
                    role="top_manager",
                    is_active=True,
                ),
            ]
        )
        return router

    def test_start_flow_shows_manager_choices(self) -> None:
        router = self._build_router()

        response = router._start_running_late_flow("employee", "emp-1")

        self.assertIn("Выбери руководителя", response.outbound.text)
        self.assertEqual([button.title for button in response.outbound.buttons[:1]], ["Петров Петр Сергеевич"])
        self.assertEqual(response.active_flow, DialogFlow.RUNNING_LATE.value)

    def test_start_flow_refreshes_directory_once_when_user_row_misses_cache(self) -> None:
        router = self._build_router()
        directory = _RefreshOnMissDirectoryService(rows=router.google_directory_service.rows)
        router.google_directory_service = directory

        response = router._start_running_late_flow("employee", "emp-1")

        self.assertIn("Выбери руководителя", response.outbound.text)
        self.assertEqual(directory.refresh_calls[:2], [False, True])

    def test_start_flow_uses_local_directory_record_without_schedule_fields(self) -> None:
        router = self._build_router()
        router.google_directory_service = _FakeDirectoryService(rows=[])
        router.employee_directory_repository = _LocalDirectoryRepository(
            [
                SimpleNamespace(
                    employee_name="Кутлуев Родион Романович",
                    employee_user_id="23325864",
                    department_name="0. Руководство",
                    manager_name="Комаровский Андрей Петрович",
                    manager_user_id="6393482",
                    role="employee",
                    is_active=True,
                ),
                SimpleNamespace(
                    employee_name="Комаровский Андрей Петрович",
                    employee_user_id="6393482",
                    department_name="1-ОКПКиПиБ",
                    role="manager",
                    is_active=True,
                ),
            ]
        )

        response = router._start_running_late_flow("employee", "23325864")

        self.assertIn("Выбери руководителя", response.outbound.text)
        self.assertIn("Комаровский Андрей Петрович", [button.title for button in response.outbound.buttons])

    def test_start_flow_uses_configured_manager_without_department_scan(self) -> None:
        router = self._build_router()
        router.google_directory_service = _FakeDirectoryService(rows=[])
        local_repository = _LocalDirectoryRepository(
            [
                SimpleNamespace(
                    employee_name="Иванов Иван Иванович",
                    employee_user_id="emp-1",
                    department_name="Отдел продаж",
                    manager_name="Петров Петр Сергеевич",
                    manager_user_id="mgr-default",
                    role="employee",
                    is_active=True,
                ),
                SimpleNamespace(
                    employee_name="Петров Петр Сергеевич",
                    employee_user_id="mgr-default",
                    department_name="Отдел продаж",
                    role="manager",
                    is_active=True,
                ),
            ]
        )
        router.employee_directory_repository = local_repository

        router._start_running_late_flow("employee", "emp-1")
        router._start_running_late_flow("employee", "emp-1")

        self.assertEqual(local_repository.list_recent_calls, 0)
        self.assertEqual(local_repository.get_by_employee_name_calls, 0)

    def test_start_flow_uses_active_substitution_for_current_manager(self) -> None:
        router = self._build_router()
        router.substitution_repository = _FakeSubstitutionRepository(
            drafts=[
                SimpleNamespace(
                    target_user_id="mgr-default",
                    target_manager="Петров Петр Сергеевич",
                    replacement_user="Смирнов Сергей Олегович",
                    replacement_user_id="mgr-alt",
                    date_from="2026-01-01",
                    date_to="2026-12-31",
                    status="approved",
                    departments=["Отдел продаж"],
                )
            ]
        )

        response = router._start_running_late_flow("employee", "emp-1")

        titles = [button.title for button in response.outbound.buttons]
        self.assertIn("Смирнов Сергей Олегович", titles)
        self.assertNotIn("Петров Петр Сергеевич", titles)

    def test_start_flow_uses_active_substitution_for_manager_even_outside_curated_departments(self) -> None:
        router = self._build_router()
        router.google_directory_service = _FakeDirectoryService(
            rows=[
                GoogleSheetsEmployeeRecord(
                    employee_name="Кутлуев Родион Романович",
                    employee_user_id="23325864",
                    department_name="0. Руководство",
                    manager_name="Комаровский Андрей Петрович",
                    manager_user_id="6393482",
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
                    role="manager",
                    is_active=True,
                ),
            ]
        )
        router.substitution_repository = _FakeSubstitutionRepository(
            drafts=[
                SimpleNamespace(
                    target_user_id="6393482",
                    target_manager="Комаровский Андрей Петрович",
                    replacement_user="Кузьменко Елена Викторовна",
                    replacement_user_id="154227986",
                    date_from="2026-01-01",
                    date_to="2026-12-31",
                    status="approved",
                    departments=["10. ОККСНР", "12. ОККНДФЛ", "13. ОККНД"],
                )
            ]
        )

        response = router._start_running_late_flow("employee", "23325864")

        button_map = {button.title: button.action for button in response.outbound.buttons}
        self.assertEqual(button_map["Кузьменко Елена Викторовна"], "late_notice.manager:154227986")
        self.assertNotIn("Комаровский Андрей Петрович", button_map)

    def test_start_flow_ignores_cancelled_substitution_for_manager(self) -> None:
        router = self._build_router()
        router.substitution_repository = _FakeSubstitutionRepository(
            drafts=[
                SimpleNamespace(
                    target_user_id="mgr-default",
                    target_manager="Петров Петр Сергеевич",
                    replacement_user="Смирнов Сергей Олегович",
                    replacement_user_id="mgr-alt",
                    date_from="2026-01-01",
                    date_to="2026-12-31",
                    status="cancelled",
                    departments=["Отдел продаж"],
                )
            ]
        )

        response = router._start_running_late_flow("employee", "emp-1")

        titles = [button.title for button in response.outbound.buttons]
        self.assertEqual(titles[:1], ["Петров Петр Сергеевич"])

    def test_full_flow_creates_late_notice_case(self) -> None:
        router = self._build_router()
        sent = Event()
        router.max_client.send_message.side_effect = lambda **kwargs: sent.set() or {"status": "ok"}
        state = UserDialogState(
            flow=DialogFlow.RUNNING_LATE.value,
            step="choose_manager",
            data={
                "employee_name": "Иванов Иван Иванович",
                "department_name": "Отдел продаж",
                "schedule_name": "Пятидневка",
                "schedule_id": "GR003",
            },
        )

        manager_response = router._handle_running_late_flow(
            "employee",
            "emp-1",
            "",
            "late_notice.manager:mgr-alt",
            state,
        )
        self.assertIn("Выбери дату опоздания", manager_response.outbound.text)
        self.assertEqual(state.step, "choose_date")

        date_response = router._handle_running_late_flow("employee", "emp-1", "", "late_notice.date:tomorrow", state)
        tomorrow = (datetime.now().date() + timedelta(days=1)).isoformat()
        self.assertIn(tomorrow, date_response.outbound.text)
        self.assertEqual(state.step, "choose_reason")

        reason_response = router._handle_running_late_flow("employee", "emp-1", "", "late_notice.reason:other", state)
        self.assertIn("Напиши причину опоздания", reason_response.outbound.text)
        self.assertEqual(state.step, "enter_other_reason")

        reason_text_response = router._handle_running_late_flow("employee", "emp-1", "Пробка на дороге", "", state)
        self.assertIn("со скольки опаздываешь", reason_text_response.outbound.text)
        self.assertEqual(state.step, "enter_time")

        result = router._handle_running_late_flow("employee", "emp-1", "08:55", "", state)
        self.assertIn("Предупреждение об опоздании отправлено на согласование.", result.outbound.text)
        self.assertEqual(result.active_flow, None)
        self.assertEqual(len(router.case_repository.created_cases), 1)

        created_case = router.case_repository.created_cases[0]
        self.assertEqual(created_case["employee_user_id"], "emp-1")
        self.assertEqual(created_case["manager_user_id"], "mgr-alt")
        self.assertEqual(created_case["case_type"], AttendanceCaseType.LATE.value)
        self.assertEqual(created_case["status"], AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value)
        self.assertEqual(created_case["event_date"], tomorrow)
        self.assertEqual(created_case["actual_start"], "08:55")
        self.assertEqual(created_case["planned_start"], "08:30")
        self.assertEqual(created_case["delay_minutes"], 0)
        self.assertEqual(created_case["source"], "late_notice")
        self.assertIn("Опаздываю с 08:55", created_case["employee_reason"])
        self.assertIn("Пробка на дороге", created_case["employee_reason"])

        self.assertEqual(
            router.approval_repository.created[0],
            {
                "case_id": 801,
                "manager_user_id": "mgr-alt",
                "manager_name": "Смирнов Сергей Олегович",
                "status": ApprovalStatus.PENDING.value,
            },
        )
        self.assertTrue(sent.wait(1))
        router.max_client.send_message.assert_called_once()
        notification = router.max_client.send_message.call_args.kwargs["text"]
        self.assertIn("Опаздывает с: 08:55", notification)
        self.assertNotIn("Отклонение от графика", notification)

    def test_invalid_time_keeps_flow_active(self) -> None:
        router = self._build_router()
        state = UserDialogState(
            flow=DialogFlow.RUNNING_LATE.value,
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

        result = router._handle_running_late_flow("employee", "emp-1", "9-15", "", state)

        self.assertIn("Нужен формат времени", result.outbound.text)
        self.assertEqual(result.active_flow, DialogFlow.RUNNING_LATE.value)
        self.assertEqual(router.case_repository.created_cases, [])
        router.max_client.send_message.assert_not_called()

    def test_back_from_reason_step_returns_to_time_step(self) -> None:
        router = self._build_router()
        state = UserDialogState(
            flow=DialogFlow.RUNNING_LATE.value,
            step="enter_time",
            data={
                "employee_name": "Иванов Иван Иванович",
                "department_name": "Отдел продаж",
                "schedule_name": "Пятидневка",
                "schedule_id": "GR003",
                "manager_user_id": "mgr-default",
                "manager_name": "Петров Петр Сергеевич",
                "notice_reason_code": "other",
                "notice_reason_label": "Пробка на дороге",
            },
        )

        result = router._handle_running_late_flow("employee", "emp-1", "", "common.back", state)

        self.assertIn("Укажи причину опоздания", result.outbound.text)
        self.assertEqual(state.step, "choose_reason")

    def test_manager_back_from_initial_running_late_returns_main_menu(self) -> None:
        router = self._build_router()
        state = UserDialogState(
            flow=DialogFlow.RUNNING_LATE.value,
            step="choose_manager",
            data={
                "employee_name": "Петров Петр Сергеевич",
                "department_name": "Отдел продаж",
                "manager_options": {"top-1": "Орлов Олег Олегович"},
            },
        )

        result = router._handle_running_late_flow("manager", "mgr-default", "", "common.back", state)

        self.assertEqual(result.outbound.text, "Главное меню готово.")
        self.assertEqual(result.active_flow, None)

    def test_old_absence_notice_reason_no_longer_starts_absence_flow(self) -> None:
        router = self._build_router()
        state = UserDialogState(
            flow=DialogFlow.RUNNING_LATE.value,
            step="choose_reason",
            data={
                "employee_name": "Иванов Иван Иванович",
                "department_name": "Отдел продаж",
                "schedule_name": "Пятидневка",
                "schedule_id": "GR003",
                "manager_user_id": "mgr-default",
                "manager_name": "Петров Петр Сергеевич",
            },
        )

        reason_response = router._handle_running_late_flow("employee", "emp-1", "", "late_notice.reason:absence_notice", state)
        self.assertIn("причина вводится вручную", reason_response.outbound.text)
        self.assertEqual(state.step, "choose_reason")
        self.assertEqual(router.case_repository.created_cases, [])

    def test_removed_specific_absence_reasons_are_not_shown(self) -> None:
        from app.bot.buttons import LATE_NOTICE_REASON_LABELS

        self.assertNotIn("vacation", LATE_NOTICE_REASON_LABELS)
        self.assertNotIn("sick_leave", LATE_NOTICE_REASON_LABELS)
        self.assertNotIn("business_trip", LATE_NOTICE_REASON_LABELS)
        self.assertNotIn("remote_day", LATE_NOTICE_REASON_LABELS)
        self.assertNotIn("absence_notice", LATE_NOTICE_REASON_LABELS)
        self.assertNotIn("approved_late", LATE_NOTICE_REASON_LABELS)
        self.assertNotIn("personal_reason", LATE_NOTICE_REASON_LABELS)
        self.assertEqual(LATE_NOTICE_REASON_LABELS["other"], "Другое")

    def test_other_reason_accepts_free_text_before_time(self) -> None:
        router = self._build_router()
        state = UserDialogState(
            flow=DialogFlow.RUNNING_LATE.value,
            step="choose_reason",
            data={
                "employee_name": "Иванов Иван Иванович",
                "department_name": "Отдел продаж",
                "schedule_name": "Пятидневка",
                "schedule_id": "GR003",
                "manager_user_id": "mgr-default",
                "manager_name": "Петров Петр Сергеевич",
            },
        )

        reason_response = router._handle_running_late_flow("employee", "emp-1", "", "late_notice.reason:other", state)
        self.assertIn("Напиши причину опоздания", reason_response.outbound.text)
        self.assertEqual(state.step, "enter_other_reason")

        text_response = router._handle_running_late_flow("employee", "emp-1", "Пробка на дороге", "", state)
        self.assertIn("со скольки опаздываешь", text_response.outbound.text)
        self.assertEqual(state.step, "enter_time")

        result = router._handle_running_late_flow("employee", "emp-1", "09:10", "", state)
        self.assertEqual(len(router.case_repository.created_cases), 1)
        self.assertIn("Пробка на дороге", router.case_repository.created_cases[0]["employee_reason"])

    def test_manager_running_late_routes_to_direct_manager(self) -> None:
        router = self._build_router()

        response = router._start_running_late_flow("manager", "mgr-default")

        titles = [button.title for button in response.outbound.buttons]
        self.assertIn("Орлов Олег Олегович", titles)

        state = UserDialogState(
            flow=DialogFlow.RUNNING_LATE.value,
            step="choose_manager",
            data={
                "employee_name": "Петров Петр Сергеевич",
                "department_name": "Отдел продаж",
                "manager_user_id": "top-1",
                "manager_name": "Орлов Олег Олегович",
            },
        )
        manager_response = router._handle_running_late_flow(
            "manager",
            "mgr-default",
            "",
            "late_notice.manager:top-1",
            state,
        )

        self.assertIn("Выбери дату опоздания", manager_response.outbound.text)
        self.assertEqual(state.step, "choose_date")
        self.assertEqual(state.data["manager_user_id"], "top-1")

    def test_manager_running_late_routes_to_configured_direct_manager(self) -> None:
        router = self._build_router()
        router.google_directory_service = _FakeDirectoryService(rows=[])
        router.employee_directory_repository = _LocalDirectoryRepository(
            [
                SimpleNamespace(
                    employee_name="Кутлуев Родион Романович",
                    employee_user_id="23325864",
                    department_name="0. Руководство",
                    manager_name="Комаровский Андрей Петрович",
                    manager_user_id="6393482",
                    role="manager",
                    is_active=True,
                ),
                SimpleNamespace(
                    employee_name="Комаровский Андрей Петрович",
                    employee_user_id="6393482",
                    department_name="1-ОКПКиПиБ",
                    manager_name="Посунько Руслан Юрьевич",
                    manager_user_id="12771658",
                    role="manager",
                    is_active=True,
                ),
                SimpleNamespace(
                    employee_name="Посунько Руслан Юрьевич",
                    employee_user_id="12771658",
                    department_name="0. Руководство",
                    role="top_manager",
                    is_active=True,
                ),
            ]
        )

        response = router._start_running_late_flow("manager", "23325864")

        titles = [button.title for button in response.outbound.buttons]
        self.assertEqual(titles[:1], ["Комаровский Андрей Петрович"])
        self.assertNotIn("Не удалось подобрать руководителя", response.outbound.text)


if __name__ == "__main__":
    unittest.main()
