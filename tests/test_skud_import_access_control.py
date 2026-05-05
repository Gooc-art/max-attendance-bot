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
        self.assertIn("только роли Служба безопасности", response.outbound.text)
        router.max_client.send_message.assert_called_once()


if __name__ == "__main__":
    unittest.main()
