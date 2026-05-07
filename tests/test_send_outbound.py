from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.bot.router import MaxWebhookRouter
from app.schemas.max import (
    MaxCallback,
    MaxMessage,
    MaxMessageBody,
    MaxOutboundButton,
    MaxOutboundMessage,
    MaxRecipient,
    MaxUpdate,
    MaxUser,
)


class SendOutboundTests(unittest.TestCase):
    def test_message_updates_do_not_duplicate_delivery_with_send_message(self) -> None:
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

        router.max_client.send_message.assert_not_called()

    def test_callback_updates_use_answer_callback(self) -> None:
        router = MaxWebhookRouter()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True

        inbound = MaxUpdate(
            update_type="message_callback",
            timestamp=1,
            callback=MaxCallback(timestamp=1, callback_id="cb-1", user=MaxUser(user_id=123, first_name="Test")),
        )

        router._send_outbound(
            inbound,
            MaxOutboundMessage(
                text="Hello",
                buttons=[MaxOutboundButton(title="Старт", action="/start")],
            ),
        )

        router.max_client.answer_callback.assert_called_once()
        kwargs = router.max_client.answer_callback.call_args.kwargs
        self.assertEqual(kwargs["callback_id"], "cb-1")


if __name__ == "__main__":
    unittest.main()
