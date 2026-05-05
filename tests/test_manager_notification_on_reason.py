from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.bot.router import MaxWebhookRouter
from app.domain.enums import AttendanceCaseStatus


class _FakeCaseRepository:
    def __init__(self):
        self.updated = []
        self.case = SimpleNamespace(
            id=101,
            employee_user_id="emp-1",
            employee_name="Иванов Иван Иванович",
            department_name="Отдел продаж",
            manager_user_id="mgr-1",
            manager_name="Петров Петр Сергеевич",
            case_type="late",
            event_date="2026-05-05",
            planned_start="08:30",
            actual_start="08:44",
            delay_minutes=14,
            employee_reason="",
            status=AttendanceCaseStatus.AWAITING_EMPLOYEE_REASON.value,
        )

    def get(self, case_id: int):
        if case_id == self.case.id:
            return self.case
        return None

    def update_reason_and_status(self, case_id: int, employee_reason: str, status: str):
        self.updated.append((case_id, employee_reason, status))
        self.case.employee_reason = employee_reason
        self.case.status = status
        return self.case


class _FakeApprovalRepository:
    def __init__(self):
        self.created = []

    def create_if_missing(self, **kwargs):
        self.created.append(kwargs)
        return 77


class ManagerNotificationTests(unittest.TestCase):
    def test_employee_reason_triggers_manager_push_notification(self) -> None:
        router = MaxWebhookRouter()
        router.case_repository = _FakeCaseRepository()
        router.approval_repository = _FakeApprovalRepository()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True

        response = router._employee_submit_reason(
            "employee",
            "emp-1",
            "employee.reason:101:personal_reason",
        )

        self.assertEqual(router.approval_repository.created[0]["manager_user_id"], "mgr-1")
        router.max_client.send_message.assert_called_once()
        kwargs = router.max_client.send_message.call_args.kwargs
        self.assertEqual(kwargs["user_id"], "mgr-1")
        self.assertIn("Новая причина по случаю #101", kwargs["text"])
        self.assertIn("Иванов Иван Иванович", kwargs["text"])
        self.assertIn("Личная причина", kwargs["text"])
        self.assertIn("Согласовать", [button.title for button in kwargs["buttons"]])
        self.assertIn("Отклонить", [button.title for button in kwargs["buttons"]])
        self.assertEqual(response.outbound.text, "Причина по случаю #101 сохранена: Личная причина.\nСтатус: На согласовании у руководителя")


if __name__ == "__main__":
    unittest.main()
