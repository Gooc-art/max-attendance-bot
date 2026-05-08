from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.bot.router import MaxWebhookRouter
from app.schemas.max import MaxAttachment, MaxAttachmentPayload, MaxMessage, MaxMessageBody, MaxRecipient, MaxUpdate, MaxUser


class _FakeRoleResolver:
    def __init__(self, role: str):
        self.role = role

    def resolve_role(self, user_id: str, chat_id: str) -> str:
        return self.role


class SkudImportAccessControlTests(unittest.TestCase):
    def test_file_upload_is_rejected_for_non_security_roles(self) -> None:
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
        self.assertIn("только службе безопасности", response.outbound.text)
        router.max_client.send_message.assert_called_once()
        kwargs = router.max_client.send_message.call_args.kwargs
        self.assertEqual(kwargs["chat_id"], 987)
        self.assertNotIn("user_id", kwargs)
        self.assertIn("службе безопасности", kwargs["text"].lower())

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
                    text="Кто я",
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
        self.assertIn("Кто я:", response.outbound.text)
        router.max_client.send_message.assert_called_once()
        kwargs = router.max_client.send_message.call_args.kwargs
        self.assertIn("Кто я:", kwargs["text"])


if __name__ == "__main__":
    unittest.main()
