from __future__ import annotations

import unittest
from threading import Event
from time import perf_counter, sleep
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.bot.actions import BotAction
from app.bot.router import MaxWebhookRouter
from app.domain.dialog_state import UserDialogState
from app.domain.enums import ApprovalStatus, AttendanceCaseStatus, DialogFlow
from app.schemas.max import MaxCallback, MaxUpdate, MaxUser


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
        self.updated = []
        self.case = _FakeCaseRepository().case
        self.case.source = "late_notice"
        self.approval = SimpleNamespace(
            id=77,
            case_id=101,
            manager_user_id="mgr-1",
            manager_name="Петров Петр Сергеевич",
            status=ApprovalStatus.PENDING.value,
            comment="",
        )

    def create_if_missing(self, **kwargs):
        self.created.append(kwargs)
        return 77

    def list_for_manager(self, manager_user_id: str, statuses=None, limit: int = 500):
        if manager_user_id != self.approval.manager_user_id:
            return []
        if statuses and self.approval.status not in statuses:
            return []
        return [(self.approval, self.case)]

    def list_for_department_names(self, department_names, statuses=None, limit: int = 500):
        return []

    def update_status(self, approval_id: int, status: str, comment: str = ""):
        self.updated.append((approval_id, status, comment))
        self.approval.status = status
        self.approval.comment = comment
        return self.approval


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

    def test_background_manager_notification_does_not_block_employee_response(self) -> None:
        router = MaxWebhookRouter()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        sent = Event()

        def slow_send(**kwargs):
            sleep(0.2)
            sent.set()

        router.max_client.send_message.side_effect = slow_send

        started = perf_counter()
        router._notify_manager_about_reason(
            _FakeCaseRepository().case,
            "Забыл карточку СКУД. Указанное время прихода: 08:44",
            77,
            background=True,
        )

        self.assertLess(perf_counter() - started, 0.1)
        self.assertTrue(sent.wait(1))

    def test_manager_notification_falls_back_to_saved_chat_id_when_user_send_fails(self) -> None:
        router = MaxWebhookRouter()
        router.bot_message_cursor_store = _FakeCursorStore(chat_id="chat-1")
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router.max_client.send_message.side_effect = [RuntimeError("forbidden"), {"status": "ok"}]

        router._notify_manager_about_reason(
            _FakeCaseRepository().case,
            "Забыл карточку СКУД. Указанное время прихода: 08:44",
            77,
        )

        self.assertEqual(router.max_client.send_message.call_count, 2)
        first_call = router.max_client.send_message.call_args_list[0].kwargs
        second_call = router.max_client.send_message.call_args_list[1].kwargs
        self.assertEqual(first_call["user_id"], "mgr-1")
        self.assertEqual(second_call["chat_id"], "chat-1")
        self.assertIn("Новая причина по случаю #101", second_call["text"])

    def test_manager_notification_logs_when_user_and_chat_send_fail(self) -> None:
        router = MaxWebhookRouter()
        router.bot_message_cursor_store = _FakeCursorStore()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router.max_client.send_message.side_effect = RuntimeError("forbidden")

        with self.assertLogs("app.bot.router", level="WARNING") as logs:
            router._notify_manager_about_reason(_FakeCaseRepository().case, "Личная причина", 77)

        self.assertIn("Failed to send manager MAX notification user_id=mgr-1", "\n".join(logs.output))

    def test_absence_notice_manager_notification_uses_saved_chat_id_fallback(self) -> None:
        router = MaxWebhookRouter()
        router.bot_message_cursor_store = _FakeCursorStore(chat_id="chat-1")
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router.max_client.send_message.side_effect = [RuntimeError("forbidden"), {"status": "ok"}]

        router._notify_manager_about_absence_notice(_FakeCaseRepository().case, "Больничный", 77)

        self.assertEqual(router.max_client.send_message.call_count, 2)
        self.assertEqual(router.max_client.send_message.call_args_list[0].kwargs["user_id"], "mgr-1")
        self.assertEqual(router.max_client.send_message.call_args_list[1].kwargs["chat_id"], "chat-1")

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

    def test_rejected_approval_notification_includes_rejection_reason(self) -> None:
        router = MaxWebhookRouter()
        router.case_repository = _FakeCaseRepository()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        approval = SimpleNamespace(
            case_id=101,
            manager_name="Петров Петр Сергеевич",
            comment="Нет подтверждения времени",
        )

        router._notify_employee_about_approval_decision(approval, approved=False)

        kwargs = router.max_client.send_message.call_args.kwargs
        self.assertIn("Причина отказа: Нет подтверждения времени", kwargs["text"])

    def test_late_notice_rejection_requires_reason_before_rejecting(self) -> None:
        router = MaxWebhookRouter()
        router.case_repository = _FakeCaseRepository()
        router.case_repository.case.source = "late_notice"
        router.approval_repository = _FakeApprovalRepository()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True

        start = router._start_approval_rejection_flow("manager", "mgr-1", 77)

        self.assertIn("Напиши причину отказа", start.outbound.text)
        self.assertEqual(start.active_flow, DialogFlow.APPROVAL_REJECTION.value)
        self.assertEqual(router.approval_repository.updated, [])

        state = UserDialogState(
            flow=DialogFlow.APPROVAL_REJECTION.value,
            step="enter_reason",
            data={"approval_id": "77"},
        )
        result = router._handle_approval_rejection_flow(
            "manager",
            "mgr-1",
            "Нет подтверждения времени",
            "",
            state,
        )

        self.assertIn("Согласование #77 отклонено", result.outbound.text)
        self.assertEqual(router.approval_repository.updated, [(77, ApprovalStatus.REJECTED.value, "Нет подтверждения времени")])
        kwargs = router.max_client.send_message.call_args.kwargs
        self.assertIn("Причина отказа: Нет подтверждения времени", kwargs["text"])

    def test_late_notice_rejection_rechecks_pending_manager_before_update(self) -> None:
        router = MaxWebhookRouter()
        router.case_repository = _FakeCaseRepository()
        router.approval_repository = _FakeApprovalRepository()
        router.approval_repository.approval.status = ApprovalStatus.APPROVED.value
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        state = UserDialogState(
            flow=DialogFlow.APPROVAL_REJECTION.value,
            step="enter_reason",
            data={"approval_id": "77"},
        )

        result = router._handle_approval_rejection_flow("manager", "mgr-1", "Поздно", "", state)

        self.assertIn("Согласование #77 не найдено или уже обработано", result.outbound.text)
        self.assertEqual(router.approval_repository.updated, [])

    def test_approval_button_cannot_approve_another_manager_case(self) -> None:
        router = MaxWebhookRouter()
        router.case_repository = _FakeCaseRepository()
        router.approval_repository = _FakeApprovalRepository()
        router.role_resolver.resolve_role = MagicMock(return_value="manager")
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router._touch_user_activity = MagicMock()

        response = router.handle_event(
            MaxUpdate(
                update_type="message_callback",
                timestamp=1,
                chat_id=123,
                callback=MaxCallback(
                    timestamp=1,
                    callback_id="cb-approve",
                    payload=f"{BotAction.APPROVAL_APPROVE_PREFIX}77",
                    user=MaxUser(user_id=999, first_name="Other"),
                ),
            )
        )

        self.assertIn("Согласование #77 не найдено", response.outbound.text)
        self.assertEqual(router.approval_repository.updated, [])

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
