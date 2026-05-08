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
    MaxWebhookResponse,
)


class SendOutboundTests(unittest.TestCase):
    def test_message_updates_send_message_for_normal_delivery(self) -> None:
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
        self.assertEqual(kwargs["chat_id"], 987)
        self.assertNotIn("user_id", kwargs)
        self.assertEqual(kwargs["text"], "Hello")

    def test_message_updates_fallback_to_user_id_when_chat_id_fails(self) -> None:
        router = MaxWebhookRouter()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router.max_client.send_message.side_effect = [RuntimeError("chat failed"), {"status": "ok"}]

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

        self.assertEqual(router.max_client.send_message.call_count, 2)
        first_call = router.max_client.send_message.call_args_list[0].kwargs
        second_call = router.max_client.send_message.call_args_list[1].kwargs
        self.assertEqual(first_call["chat_id"], 987)
        self.assertEqual(second_call["user_id"], 123)

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

    def test_callback_updates_without_message_still_route_actions(self) -> None:
        router = MaxWebhookRouter()
        payload = MaxUpdate(
            update_type="message_callback",
            timestamp=1,
            chat_id=777,
            callback=MaxCallback(
                timestamp=1,
                callback_id="cb-2",
                payload="menu.main",
                user=MaxUser(user_id=456, first_name="Test"),
            ),
        )

        event = router._normalize_event(payload)

        self.assertEqual(event["user_id"], "456")
        self.assertEqual(event["chat_id"], "777")
        self.assertEqual(event["action"], "menu.main")

    def test_callback_routes_division_reports_action(self) -> None:
        router = MaxWebhookRouter()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = False
        router.role_resolver.resolve_role = MagicMock(return_value="admin")
        router._division_reports = MagicMock(
            return_value=MaxWebhookResponse(
                ok=True,
                role="admin",
                menu=[],
                outbound=MaxOutboundMessage(text="done", buttons=[]),
                active_flow=None,
            )
        )

        payload = MaxUpdate(
            update_type="message_callback",
            timestamp=1,
            chat_id=777,
            callback=MaxCallback(
                timestamp=1,
                callback_id="cb-division",
                payload="menu.division_reports",
                user=MaxUser(user_id=456, first_name="Test"),
            ),
        )

        response = router.handle_event(payload)

        router._division_reports.assert_called_once_with("admin", "456", "777")
        self.assertEqual(response.outbound.text, "done")


if __name__ == "__main__":
    unittest.main()
