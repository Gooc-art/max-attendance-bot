from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.bot.router import MaxWebhookRouter
from app.schemas.max import MaxMessage, MaxMessageBody, MaxRecipient, MaxUpdate, MaxUser, MaxOutboundButton, MaxOutboundMessage


class SendOutboundTests(unittest.TestCase):
    def test_message_updates_use_user_id_for_delivery(self) -> None:
        router = MaxWebhookRouter()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True

        inbound = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=1,
                body=MaxMessageBody(mid="m1", seq=1, text="/start"),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        router._send_outbound(
            inbound,
            MaxOutboundMessage(
                text="Hello",
                buttons=[MaxOutboundButton(title="Старт", action="/start")],
            ),
        )

        router.max_client.send_message.assert_called_once()
        kwargs = router.max_client.send_message.call_args.kwargs
        self.assertEqual(kwargs["user_id"], 123)
        self.assertEqual(kwargs["chat_id"], 987)


if __name__ == "__main__":
    unittest.main()
