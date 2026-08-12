from __future__ import annotations

import unittest
from datetime import datetime
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.bot.actions import BotAction
from app.bot.router import MaxWebhookRouter
from app.domain.dialog_state import UserDialogState
from app.domain.enums import ApprovalStatus, AttendanceCaseStatus, AttendanceCaseType, DialogFlow
from app.services.skud_import import SkudImportService
from tests.test_running_late_flow import (
    _FakeApprovalRepository,
    _FakeCaseRepository,
    _FakeDirectoryService,
    _FakeScheduleService,
    _LocalDirectoryRepository,
)
from tests.test_skud_import import (
    _FakeAttendanceDayRecordRepository,
    _FakeEmployeeDirectoryRepository,
    _FakeGoogleSheetsScheduleService,
    _FakeSkudImportRepository,
    _FakeSubstitutionRepository,
)


class _ShortLeaveCaseRepository:
    def __init__(self):
        self.created = []
        self.short_leave_match = SimpleNamespace(id=77, planned_start="12:30")
        self.updated_short_leave_matches = []

    def create_case(self, **kwargs):
        self.created.append(kwargs)
        return len(self.created)

    def find_matching_late_notice(self, **kwargs):
        return None

    def find_matching_short_leave_notice(self, *, employee_user_id: str, event_date: str):
        if employee_user_id == "max_010" and event_date == "2026-05-04":
            return self.short_leave_match
        return None

    def update_short_leave_skud_match(self, case_id: int, *, return_time: str):
        row = SimpleNamespace(id=case_id, actual_start=return_time, source="short_leave_notice_matched")
        self.updated_short_leave_matches.append(row)
        return row


class ShortLeaveFlowTests(unittest.TestCase):
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
                SimpleNamespace(
                    employee_name="Иванов Иван Иванович",
                    employee_user_id="emp-1",
                    department_name="Отдел продаж",
                    manager_name="Петров Петр Сергеевич",
                    manager_user_id="mgr-1",
                    schedule_name="Пятидневка",
                    schedule_id="GR003",
                    role="employee",
                    is_active=True,
                ),
                SimpleNamespace(
                    employee_name="Петров Петр Сергеевич",
                    employee_user_id="mgr-1",
                    department_name="Отдел продаж",
                    manager_name="Орлов Олег Олегович",
                    manager_user_id="top-1",
                    role="manager",
                    is_active=True,
                ),
            ]
        )
        return router

    def test_start_flow_shows_manager_choices(self) -> None:
        router = self._build_router()

        response = router._start_short_leave_flow("employee", "emp-1")

        self.assertIn("Выбери руководителя", response.outbound.text)
        self.assertEqual([button.title for button in response.outbound.buttons[:1]], ["Петров Петр Сергеевич"])
        self.assertEqual(response.active_flow, DialogFlow.SHORT_LEAVE.value)

    def test_full_flow_accepts_custom_reason_and_creates_approval(self) -> None:
        router = self._build_router()
        sent = Event()
        router.max_client.send_message.side_effect = lambda **kwargs: sent.set() or {"status": "ok"}
        state = UserDialogState(
            flow=DialogFlow.SHORT_LEAVE.value,
            step="choose_manager",
            data={
                "employee_name": "Иванов Иван Иванович",
                "department_name": "Отдел продаж",
                "schedule_name": "Пятидневка",
                "schedule_id": "GR003",
                "manager_options": {"mgr-1": "Петров Петр Сергеевич"},
            },
        )

        manager_response = router._handle_short_leave_flow("employee", "emp-1", "", "short_leave.manager:mgr-1", state)
        self.assertIn("во сколько уходишь", manager_response.outbound.text)
        self.assertEqual(state.step, "enter_leave_from")

        leave_response = router._handle_short_leave_flow("employee", "emp-1", "12:30", "", state)
        self.assertIn("Когда планируешь вернуться", leave_response.outbound.text)
        self.assertEqual(state.step, "enter_expected_return")

        return_response = router._handle_short_leave_flow("employee", "emp-1", "14:00", "", state)
        self.assertIn("Напиши причину", return_response.outbound.text)
        self.assertEqual(state.step, "enter_reason")

        result = router._handle_short_leave_flow("employee", "emp-1", "Нужно в МФЦ за документами", "", state)

        self.assertIn("отправлена на согласование", result.outbound.text)
        self.assertEqual(result.active_flow, None)
        self.assertEqual(len(router.case_repository.created_cases), 1)
        created_case = router.case_repository.created_cases[0]
        self.assertEqual(created_case["employee_user_id"], "emp-1")
        self.assertEqual(created_case["manager_user_id"], "mgr-1")
        self.assertEqual(created_case["case_type"], AttendanceCaseType.SHORT_LEAVE.value)
        self.assertEqual(created_case["status"], AttendanceCaseStatus.AWAITING_MANAGER_APPROVAL.value)
        self.assertEqual(created_case["event_date"], datetime.now().date().isoformat())
        self.assertEqual(created_case["planned_start"], "12:30")
        self.assertEqual(created_case["actual_start"], "-")
        self.assertEqual(created_case["delay_minutes"], 0)
        self.assertEqual(created_case["source"], "short_leave_notice")
        self.assertIn("Отпроситься с 12:30 до 14:00", created_case["employee_reason"])
        self.assertIn("Нужно в МФЦ за документами", created_case["employee_reason"])
        self.assertEqual(
            router.approval_repository.created[0],
            {
                "case_id": 801,
                "manager_user_id": "mgr-1",
                "manager_name": "Петров Петр Сергеевич",
                "status": ApprovalStatus.PENDING.value,
            },
        )
        self.assertTrue(sent.wait(1))

    def test_skud_import_matches_return_entry_after_leave_time(self) -> None:
        access_report = (
            "Отчет по проходам\n"
            "Ф.И.О;Таб.№;Подразделение;Подразделение;Дата и время;Точка;Событие;Зона\n"
            "Иванова Анна Сергеевна;;;Отдел продаж;04.05.2026 08:20:00;Вход;Проход;Здание\n"
            "Иванова Анна Сергеевна;;;Отдел продаж;04.05.2026 12:30:00;Выход;Проход;Внешний мир\n"
            "Иванова Анна Сергеевна;;;Отдел продаж;04.05.2026 14:10:00;Вход;Проход;Здание\n"
            "Иванова Анна Сергеевна;;;Отдел продаж;04.05.2026 17:20:00;Выход;Проход;Внешний мир\n"
        ).encode("utf-8")
        case_repo = _ShortLeaveCaseRepository()

        with patch("app.services.skud_import.AttendanceCaseRepository", lambda: case_repo), patch(
            "app.services.skud_import.EmployeeDirectoryRepository", _FakeEmployeeDirectoryRepository
        ), patch(
            "app.services.skud_import.SkudImportRepository", _FakeSkudImportRepository
        ), patch(
            "app.services.skud_import.AttendanceDayRecordRepository", _FakeAttendanceDayRecordRepository
        ), patch(
            "app.services.skud_import.GoogleSheetsDirectoryService.from_settings",
            return_value=SimpleNamespace(
                get_by_employee_name=lambda employee_name: SimpleNamespace(
                    employee_name=employee_name,
                    employee_user_id="max_010",
                    manager_name="Петров Петр Сергеевич",
                    manager_user_id="max_020",
                    department_name="Отдел продаж",
                    schedule_name="Пятидневка - Девушки 08:30-12:30 / 14:00-17:15",
                    schedule_id="ГР003",
                    role="employee",
                    is_active=True,
                )
            ),
        ), patch(
            "app.services.skud_import.GoogleSheetsScheduleService.from_settings",
            return_value=_FakeGoogleSheetsScheduleService(),
        ), patch(
            "app.services.skud_import.SubstitutionRepository",
            return_value=_FakeSubstitutionRepository(),
        ):
            service = SkudImportService()
            result = service.import_csv(filename="report.txt", content=access_report, created_by_user_id="sec_001")

        self.assertEqual(result.created_cases, 0)
        self.assertEqual(case_repo.created, [])
        self.assertEqual(len(case_repo.updated_short_leave_matches), 1)
        self.assertEqual(case_repo.updated_short_leave_matches[0].id, 77)
        self.assertEqual(case_repo.updated_short_leave_matches[0].actual_start, "14:10")
        self.assertEqual(case_repo.updated_short_leave_matches[0].source, "short_leave_notice_matched")


if __name__ == "__main__":
    unittest.main()
