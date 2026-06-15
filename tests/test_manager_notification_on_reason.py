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


class _FakeDirectoryService:
    def __init__(self, record=None):
        self.record = record

    def get_by_employee_name(self, employee_name: str):
        if self.record is not None and self.record.employee_name == employee_name:
            return self.record
        return None


class _FakeCursorStore:
    def __init__(self, chat_id: str = ""):
        self.chat_id = chat_id

    def get_chat_id_for_user(self, user_id: str):
        return self.chat_id


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
        self.assertIn("Открыть", [button.title for button in kwargs["buttons"]])
        self.assertNotIn("Согласовать", [button.title for button in kwargs["buttons"]])
        self.assertEqual(response.outbound.text, "Причина по случаю #101 сохранена: Личная причина.\nСтатус: На согласовании у руководителя")

    def test_approval_decision_triggers_employee_push_notification(self) -> None:
        router = MaxWebhookRouter()
        router.case_repository = _FakeCaseRepository()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        approval = SimpleNamespace(case_id=101, manager_name="Петров Петр Сергеевич")

        router._notify_employee_about_approval_decision(approval, approved=True)

        router.max_client.send_message.assert_called_once()
        kwargs = router.max_client.send_message.call_args.kwargs
        self.assertEqual(kwargs["user_id"], "emp-1")
        self.assertIn("Твоя заявка согласована", kwargs["text"])
        self.assertIn("Кто согласовал: Петров Петр Сергеевич", kwargs["text"])
        self.assertIn("Мои статусы", [button.title for button in kwargs["buttons"]])

    def test_rejected_approval_triggers_employee_push_notification(self) -> None:
        router = MaxWebhookRouter()
        router.case_repository = _FakeCaseRepository()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        approval = SimpleNamespace(case_id=101, manager_name="Петров Петр Сергеевич")

        router._notify_employee_about_approval_decision(approval, approved=False)

        router.max_client.send_message.assert_called_once()
        kwargs = router.max_client.send_message.call_args.kwargs
        self.assertEqual(kwargs["user_id"], "emp-1")
        self.assertIn("Твоя заявка отклонена", kwargs["text"])
        self.assertIn("Кто отклонил: Петров Петр Сергеевич", kwargs["text"])

    def test_approval_decision_uses_directory_when_case_has_no_employee_user_id(self) -> None:
        router = MaxWebhookRouter()
        router.case_repository = _FakeCaseRepository()
        router.case_repository.case.employee_user_id = ""
        router.google_directory_service = _FakeDirectoryService(
            SimpleNamespace(
                employee_name="Иванов Иван Иванович",
                employee_user_id="emp-from-directory",
            )
        )
        router.employee_directory_repository = _FakeDirectoryService()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        approval = SimpleNamespace(case_id=101, manager_name="Петров Петр Сергеевич")

        router._notify_employee_about_approval_decision(approval, approved=False)

        router.max_client.send_message.assert_called_once()
        kwargs = router.max_client.send_message.call_args.kwargs
        self.assertEqual(kwargs["user_id"], "emp-from-directory")
        self.assertIn("Твоя заявка отклонена", kwargs["text"])

    def test_approval_decision_falls_back_to_saved_chat_id_when_user_send_fails(self) -> None:
        router = MaxWebhookRouter()
        router.case_repository = _FakeCaseRepository()
        router.bot_message_cursor_store = _FakeCursorStore(chat_id="chat-1")
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router.max_client.send_message.side_effect = [RuntimeError("forbidden"), {"status": "ok"}]
        approval = SimpleNamespace(case_id=101, manager_name="Петров Петр Сергеевич")

        router._notify_employee_about_approval_decision(approval, approved=False)

        self.assertEqual(router.max_client.send_message.call_count, 2)
        first_call = router.max_client.send_message.call_args_list[0].kwargs
        second_call = router.max_client.send_message.call_args_list[1].kwargs
        self.assertEqual(first_call["user_id"], "emp-1")
        self.assertEqual(second_call["chat_id"], "chat-1")
        self.assertIn("Твоя заявка отклонена", second_call["text"])


if __name__ == "__main__":
    unittest.main()
