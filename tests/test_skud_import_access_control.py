from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.bot.router import MaxWebhookRouter
from app.domain.dialog_state import UserDialogState
from app.schemas.max import MaxAttachment, MaxAttachmentPayload, MaxMessage, MaxMessageBody, MaxRecipient, MaxUpdate, MaxUser


class _FakeRoleResolver:
    def __init__(self, role: str):
        self.role = role

    def resolve_role(self, user_id: str, chat_id: str) -> str:
        return self.role


class SkudImportAccessControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self._marker_claim = patch("app.repositories.runtime_marker_repository.RuntimeMarkerRepository.claim", return_value=True)
        self._marker_complete = patch("app.repositories.runtime_marker_repository.RuntimeMarkerRepository.complete")
        self._marker_release = patch("app.repositories.runtime_marker_repository.RuntimeMarkerRepository.release")
        self._marker_claim.start()
        self._marker_complete.start()
        self._marker_release.start()
        self.addCleanup(self._marker_release.stop)
        self.addCleanup(self._marker_complete.stop)
        self.addCleanup(self._marker_claim.stop)

    def test_file_upload_is_rejected_for_employee_role(self) -> None:
        router = MaxWebhookRouter()
        router.role_resolver = _FakeRoleResolver("employee")
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router.max_file_import_service = MagicMock()

        payload = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=1,
                body=MaxMessageBody(
                    mid="m1",
                    seq=1,
                    text="Отчет",
                    attachments=[
                        MaxAttachment(
                            type="file",
                            filename="Отчет по проходам.xlsx",
                            payload=MaxAttachmentPayload(url="https://example.com/report.xlsx"),
                        )
                    ],
                ),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        response = router.handle_event(payload)

        router.max_file_import_service.import_attachments.assert_not_called()
        self.assertIn("только руководителям", response.outbound.text)
        router.max_client.send_message.assert_called_once()
        kwargs = router.max_client.send_message.call_args.kwargs
        self.assertEqual(kwargs["chat_id"], 987)
        self.assertNotIn("user_id", kwargs)
        self.assertIn("службе безопасности", kwargs["text"].lower())
        self.assertIn("главным руководителям", kwargs["text"].lower())

    def test_manager_upload_help_returns_to_reports(self) -> None:
        router = MaxWebhookRouter()

        response = router._security_import_help("manager", "123")

        actions = [button.action for button in response.outbound.buttons]
        self.assertIn("manager.reports_section", actions)
        self.assertNotIn("security.skud_section", actions)

    def test_file_upload_passes_message_id_to_import_service(self) -> None:
        router = MaxWebhookRouter()
        router.role_resolver = _FakeRoleResolver("security")
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router.max_client.send_message = MagicMock()
        router.max_file_import_service = MagicMock()
        router.max_file_import_service.import_attachments.return_value = []

        payload = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=1,
                body=MaxMessageBody(
                    mid="m9",
                    seq=1,
                    text="Отчет",
                    attachments=[
                        MaxAttachment(
                            type="file",
                            filename="Отчет по проходам.xlsx",
                            payload=MaxAttachmentPayload(url="https://example.com/report.xlsx"),
                        )
                    ],
                ),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        router.handle_event(payload)

        router.max_file_import_service.import_attachments.assert_called_once()
        kwargs = router.max_file_import_service.import_attachments.call_args.kwargs
        self.assertEqual(kwargs["created_by_user_id"], "123")
        self.assertEqual(kwargs["message_id"], "m9")

    def test_document_attachment_is_treated_as_supported_upload(self) -> None:
        router = MaxWebhookRouter()
        router.role_resolver = _FakeRoleResolver("security")
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router.max_client.send_message = MagicMock()
        router.max_file_import_service = MagicMock()
        router.max_file_import_service.import_attachments.return_value = []

        payload = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=1,
                body=MaxMessageBody(
                    mid="m10",
                    seq=1,
                    text="Отчет",
                    attachments=[
                        MaxAttachment(
                            type="document",
                            filename="Отчет по проходам.xlsx",
                            payload=MaxAttachmentPayload(token="abc"),
                        )
                    ],
                ),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        router.handle_event(payload)

        router.max_file_import_service.import_attachments.assert_called_once()
        kwargs = router.max_file_import_service.import_attachments.call_args.kwargs
        self.assertEqual(kwargs["message_id"], "m10")

    def test_successful_security_upload_returns_thanks_and_processing_text(self) -> None:
        router = MaxWebhookRouter()
        router.role_resolver = _FakeRoleResolver("security")
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router.max_client.send_message = MagicMock()
        router.max_file_import_service = MagicMock()
        router.max_file_import_service.import_attachments.return_value = [
            SimpleNamespace(message="Импорт завершен: 12 сотрудников, 3 случая.")
        ]

        payload = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=1,
                body=MaxMessageBody(
                    mid="m10",
                    seq=1,
                    text="Отчет",
                    attachments=[
                        MaxAttachment(
                            type="document",
                            filename="Отчет по проходам.xlsx",
                            payload=MaxAttachmentPayload(token="abc"),
                        )
                    ],
                ),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        response = router.handle_event(payload)

        self.assertIn("Спасибо, файл получен", response.outbound.text)
        self.assertIn("Обрабатываю выгрузку СКУД", response.outbound.text)
        self.assertIn("Импорт завершен", response.outbound.text)

    def test_top_manager_file_upload_is_allowed(self) -> None:
        router = MaxWebhookRouter()
        router.role_resolver = _FakeRoleResolver("top_manager")
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router.max_client.send_message = MagicMock()
        router.max_file_import_service = MagicMock()
        router.max_file_import_service.import_attachments.return_value = [
            SimpleNamespace(message="Импорт завершен: 7 сотрудников, 1 случай.")
        ]

        payload = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=1,
                body=MaxMessageBody(
                    mid="m13",
                    seq=1,
                    text="Отчет",
                    attachments=[
                        MaxAttachment(
                            type="document",
                            filename="Отчет по проходам.xlsx",
                            payload=MaxAttachmentPayload(token="abc"),
                        )
                    ],
                ),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        response = router.handle_event(payload)

        router.max_file_import_service.import_attachments.assert_called_once()
        self.assertIn("Спасибо, файл получен", response.outbound.text)
        self.assertIn("Импорт завершен", response.outbound.text)

    def test_manager_file_upload_is_allowed(self) -> None:
        router = MaxWebhookRouter()
        router.role_resolver = _FakeRoleResolver("manager")
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router.max_file_import_service = MagicMock()
        router.max_file_import_service.import_attachments.return_value = [
            SimpleNamespace(message="Импорт завершен: 4 сотрудника, 1 случай.")
        ]

        payload = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=1,
                body=MaxMessageBody(
                    mid="m-manager",
                    seq=1,
                    text="Отчет",
                    attachments=[
                        MaxAttachment(
                            type="document",
                            filename="Отчет по проходам.xlsx",
                            payload=MaxAttachmentPayload(token="abc"),
                        )
                    ],
                ),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        response = router.handle_event(payload)

        router.max_file_import_service.import_attachments.assert_called_once()
        self.assertIn("Спасибо, файл получен", response.outbound.text)
        self.assertIn("Импорт завершен", response.outbound.text)

    def test_admin_file_upload_is_allowed(self) -> None:
        router = MaxWebhookRouter()
        router.role_resolver = _FakeRoleResolver("admin")
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router.max_file_import_service = MagicMock()
        router.max_file_import_service.import_attachments.return_value = [
            SimpleNamespace(message="Импорт завершен: 5 сотрудников, 0 случаев.")
        ]

        payload = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=1,
                body=MaxMessageBody(
                    mid="m-admin",
                    seq=1,
                    text="Отчет",
                    attachments=[
                        MaxAttachment(
                            type="document",
                            filename="Отчет по проходам.xlsx",
                            payload=MaxAttachmentPayload(token="abc"),
                        )
                    ],
                ),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        response = router.handle_event(payload)

        router.max_file_import_service.import_attachments.assert_called_once()
        self.assertIn("Спасибо, файл получен", response.outbound.text)
        self.assertIn("Импорт завершен", response.outbound.text)

    def test_file_upload_interrupts_active_dialog_flow(self) -> None:
        router = MaxWebhookRouter()
        router.role_resolver = _FakeRoleResolver("security")
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router.max_file_import_service = MagicMock()
        router.max_file_import_service.import_attachments.return_value = [
            SimpleNamespace(message="Импорт завершен: 5 сотрудников, 0 случаев.")
        ]
        payload = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=1,
                body=MaxMessageBody(
                    mid="m-active",
                    seq=1,
                    text="",
                    attachments=[
                        MaxAttachment(
                            type="file",
                            filename="Отчет.xlsx",
                            payload=MaxAttachmentPayload(url="https://example.com/report.xlsx"),
                        )
                    ],
                ),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        with patch("app.bot.router.dialog_state_store.get") as get_state:
            with patch("app.bot.router.dialog_state_store.reset") as reset_state:
                get_state.return_value = UserDialogState(flow="report_period", step="date_from")
                response = router.handle_event(payload)

        reset_state.assert_called_once_with("123")
        router.max_file_import_service.import_attachments.assert_called_once()
        self.assertIn("Импорт завершен", response.outbound.text)

    def test_unknown_attachment_type_returns_explanatory_message(self) -> None:
        router = MaxWebhookRouter()
        router.role_resolver = _FakeRoleResolver("security")
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router.max_client.send_message = MagicMock()
        router.max_file_import_service = MagicMock()

        payload = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=1,
                body=MaxMessageBody(
                    mid="m11",
                    seq=1,
                    text="",
                    attachments=[
                        MaxAttachment(
                            type="sticker",
                            filename="sticker.webp",
                        )
                    ],
                ),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        response = router.handle_event(payload)

        self.assertIn("не умею его разобрать", response.outbound.text)
        router.max_file_import_service.import_attachments.assert_not_called()
        router.max_client.send_message.assert_called_once()

    def test_inline_keyboard_attachment_does_not_override_text_buttons(self) -> None:
        router = MaxWebhookRouter()
        router.role_resolver = _FakeRoleResolver("admin")
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router.max_client.send_message = MagicMock()
        router.max_file_import_service = MagicMock()

        payload = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=1,
                body=MaxMessageBody(
                    mid="m12",
                    seq=1,
                    text="Обо мне",
                    attachments=[
                        MaxAttachment(
                            type="inline_keyboard",
                            filename="inline_keyboard",
                        )
                    ],
                ),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        response = router.handle_event(payload)

        router.max_file_import_service.import_attachments.assert_not_called()
        self.assertIn("Обо мне:", response.outbound.text)
        router.max_client.send_message.assert_called_once()
        kwargs = router.max_client.send_message.call_args.kwargs
        self.assertIn("Обо мне:", kwargs["text"])


if __name__ == "__main__":
    unittest.main()
