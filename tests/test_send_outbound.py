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
    def _build_router(self) -> MaxWebhookRouter:
        router = MaxWebhookRouter()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = True
        router.bot_message_cursor_store = MagicMock()
        router.bot_message_cursor_store.get.return_value = None
        router.bot_message_cursor_store.get_chat_id_for_user.return_value = None
        return router

    def test_message_updates_send_message_for_normal_delivery(self) -> None:
        router = self._build_router()
        router.max_client.send_message.return_value = {"mid": "bot-1"}

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

        router.max_client.delete_message.assert_not_called()
        router.max_client.send_message.assert_called_once()
        kwargs = router.max_client.send_message.call_args.kwargs
        self.assertEqual(kwargs["chat_id"], 987)
        self.assertNotIn("user_id", kwargs)
        self.assertEqual(kwargs["text"], "Hello")
        self.assertEqual(router.bot_message_cursor_store.set.call_count, 2)
        router.bot_message_cursor_store.set.assert_any_call(
            conversation_key="chat:987",
            chat_id="987",
            user_id="123",
            message_id="bot-1",
        )
        router.bot_message_cursor_store.set.assert_any_call(
            conversation_key="user:123",
            chat_id="987",
            user_id="123",
            message_id="bot-1",
        )

    def test_message_updates_fallback_to_user_id_when_chat_id_fails(self) -> None:
        router = self._build_router()
        router.max_client.send_message.side_effect = [RuntimeError("chat failed"), {"status": "ok", "mid": "bot-2"}]

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
        self.assertEqual(router.bot_message_cursor_store.set.call_count, 2)
        router.bot_message_cursor_store.set.assert_any_call(
            conversation_key="chat:987",
            chat_id="987",
            user_id="123",
            message_id="bot-2",
        )
        router.bot_message_cursor_store.set.assert_any_call(
            conversation_key="user:123",
            chat_id="987",
            user_id="123",
            message_id="bot-2",
        )

    def test_fast_mode_skips_previous_message_delete(self) -> None:
        router = self._build_router()
        router.delete_previous_message = False
        router.bot_message_cursor_store.get.return_value = "previous-mid"
        router.max_client.send_message.return_value = {"mid": "bot-fast"}

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

        router._send_outbound(inbound, MaxOutboundMessage(text="Hello"))

        router.max_client.delete_message.assert_not_called()
        router.max_client.soft_clear_message.assert_not_called()
        router.max_client.send_message.assert_called_once()

    def test_callback_updates_current_message_without_visible_send(self) -> None:
        router = self._build_router()

        inbound = MaxUpdate(
            update_type="message_callback",
            timestamp=1,
            chat_id=987,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=1,
                body=MaxMessageBody(mid="bot-card", seq=1, text="old"),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
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
        callback_kwargs = router.max_client.answer_callback.call_args.kwargs
        self.assertEqual(callback_kwargs["callback_id"], "cb-1")
        self.assertEqual(callback_kwargs["new_text"], "Hello")
        self.assertEqual(callback_kwargs["buttons"][0].title, "Старт")
        router.max_client.send_message.assert_not_called()
        self.assertEqual(router.bot_message_cursor_store.set.call_count, 2)
        router.bot_message_cursor_store.set.assert_any_call(
            conversation_key="chat:987",
            chat_id="987",
            user_id="123",
            message_id="bot-card",
        )
        router.bot_message_cursor_store.set.assert_any_call(
            conversation_key="user:123",
            chat_id="987",
            user_id="123",
            message_id="bot-card",
        )

    def test_callback_still_sends_visible_message_when_answer_callback_fails(self) -> None:
        router = self._build_router()
        router.max_client.answer_callback.side_effect = RuntimeError("answer failed")
        router.max_client.send_message.return_value = {"status": "ok", "mid": "bot-3"}

        inbound = MaxUpdate(
            update_type="message_callback",
            timestamp=1,
            chat_id=987,
            callback=MaxCallback(timestamp=1, callback_id="cb-1", payload="approval.open", user=MaxUser(user_id=123, first_name="Test")),
        )

        router._send_outbound(
            inbound,
            MaxOutboundMessage(
                text="Hello",
                buttons=[MaxOutboundButton(title="Старт", action="/start")],
            ),
        )

        router.max_client.answer_callback.assert_called_once()
        router.max_client.send_message.assert_called_once()
        kwargs = router.max_client.send_message.call_args.kwargs
        self.assertEqual(kwargs["chat_id"], 987)
        self.assertEqual(router.bot_message_cursor_store.set.call_count, 2)
        router.bot_message_cursor_store.set.assert_any_call(
            conversation_key="chat:987",
            chat_id="987",
            user_id="123",
            message_id="bot-3",
        )
        router.bot_message_cursor_store.set.assert_any_call(
            conversation_key="user:123",
            chat_id="987",
            user_id="123",
            message_id="bot-3",
        )

    def test_main_menu_callback_updates_current_message(self) -> None:
        router = self._build_router()

        inbound = MaxUpdate(
            update_type="message_callback",
            timestamp=1,
            chat_id=987,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=1,
                body=MaxMessageBody(mid="bot-main-card", seq=1, text="old"),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
            callback=MaxCallback(
                timestamp=1,
                callback_id="cb-main",
                payload="menu.main",
                user=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        router._send_outbound(
            inbound,
            MaxOutboundMessage(
                text="Главное меню готово.",
                buttons=[MaxOutboundButton(title="Старт", action="/start")],
            ),
        )

        router.max_client.send_message.assert_not_called()
        router.max_client.answer_callback.assert_called_once()
        answer_kwargs = router.max_client.answer_callback.call_args.kwargs
        self.assertEqual(answer_kwargs["callback_id"], "cb-main")
        self.assertEqual(answer_kwargs["new_text"], "Главное меню готово.")
        self.assertEqual(answer_kwargs["buttons"][0].title, "Старт")
        self.assertEqual(router.bot_message_cursor_store.set.call_count, 2)
        router.bot_message_cursor_store.set.assert_any_call(
            conversation_key="chat:987",
            chat_id="987",
            user_id="123",
            message_id="bot-main-card",
        )
        router.bot_message_cursor_store.set.assert_any_call(
            conversation_key="user:123",
            chat_id="987",
            user_id="123",
            message_id="bot-main-card",
        )

    def test_callback_without_chat_id_answers_with_embedded_message(self) -> None:
        router = self._build_router()

        inbound = MaxUpdate(
            update_type="message_callback",
            timestamp=1,
            callback=MaxCallback(
                timestamp=1,
                callback_id="cb-inline",
                payload="menu.bot_activity",
                user=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        router._send_outbound(
            inbound,
            MaxOutboundMessage(
                text="Входы в бот",
                buttons=[MaxOutboundButton(title="Назад", action="top.summary")],
            ),
        )

        router.max_client.answer_callback.assert_called_once()
        callback_kwargs = router.max_client.answer_callback.call_args.kwargs
        self.assertEqual(callback_kwargs["callback_id"], "cb-inline")
        self.assertEqual(callback_kwargs["new_text"], "Входы в бот")
        self.assertEqual(callback_kwargs["buttons"][0].title, "Назад")
        router.max_client.send_message.assert_not_called()
        router.bot_message_cursor_store.set.assert_not_called()

    def test_previous_bot_message_is_deleted_before_sending_new_one(self) -> None:
        router = self._build_router()
        router.bot_message_cursor_store.get.return_value = "bot-prev"
        router.max_client.send_message.return_value = {"mid": "bot-next"}

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

        router.max_client.delete_message.assert_called_once_with("bot-prev")
        router.max_client.send_message.assert_called_once()
        self.assertEqual(router.bot_message_cursor_store.set.call_count, 2)
        router.bot_message_cursor_store.set.assert_any_call(
            conversation_key="chat:987",
            chat_id="987",
            user_id="123",
            message_id="bot-next",
        )
        router.bot_message_cursor_store.set.assert_any_call(
            conversation_key="user:123",
            chat_id="987",
            user_id="123",
            message_id="bot-next",
        )

    def test_previous_bot_message_falls_back_to_soft_clear_when_delete_fails(self) -> None:
        router = self._build_router()
        router.bot_message_cursor_store.get.return_value = "bot-prev"
        router.max_client.delete_message.side_effect = RuntimeError("delete forbidden")
        router.max_client.send_message.return_value = {"mid": "bot-next"}

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

        router.max_client.delete_message.assert_called_once_with("bot-prev")
        router.max_client.soft_clear_message.assert_called_once_with("bot-prev")
        router.max_client.send_message.assert_called_once()

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

    def test_callback_without_chat_id_uses_embedded_callback_message(self) -> None:
        router = self._build_router()

        inbound = MaxUpdate(
            update_type="message_callback",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=456),
                timestamp=1,
                body=MaxMessageBody(mid="bot-card", seq=1, text="old"),
                sender=MaxUser(user_id=456, first_name="Test"),
            ),
            callback=MaxCallback(
                timestamp=1,
                callback_id="cb-user",
                payload="menu.main",
                user=MaxUser(user_id=456, first_name="Test"),
            ),
        )

        router._send_outbound(
            inbound,
            MaxOutboundMessage(
                text="Меню",
                buttons=[MaxOutboundButton(title="Старт", action="/start")],
            ),
        )

        callback_kwargs = router.max_client.answer_callback.call_args.kwargs
        self.assertEqual(callback_kwargs["callback_id"], "cb-user")
        self.assertEqual(callback_kwargs["new_text"], "Меню")
        self.assertEqual(callback_kwargs["buttons"][0].title, "Старт")
        router.max_client.send_message.assert_not_called()
        router.bot_message_cursor_store.set.assert_called_once_with(
            conversation_key="user:456",
            chat_id="",
            user_id="456",
            message_id="bot-card",
        )

    def test_previous_message_is_not_deleted_when_callback_has_no_chat_id(self) -> None:
        router = self._build_router()

        def _cursor_get(key: str):
            return {"user:456": "bot-prev"}.get(key)

        router.bot_message_cursor_store.get.side_effect = _cursor_get

        inbound = MaxUpdate(
            update_type="message_callback",
            timestamp=1,
            callback=MaxCallback(
                timestamp=1,
                callback_id="cb-user",
                payload="menu.main",
                user=MaxUser(user_id=456, first_name="Test"),
            ),
        )

        router._send_outbound(
            inbound,
            MaxOutboundMessage(
                text="Меню",
                buttons=[MaxOutboundButton(title="Старт", action="/start")],
            ),
        )

        router.max_client.delete_message.assert_not_called()

    def test_callback_without_chat_id_uses_embedded_message_even_with_saved_chat(self) -> None:
        router = self._build_router()
        router.bot_message_cursor_store.get_chat_id_for_user.return_value = "987"

        def _cursor_get(key: str):
            return {"chat:987": "bot-prev", "user:456": "bot-prev"}.get(key)

        router.bot_message_cursor_store.get.side_effect = _cursor_get

        inbound = MaxUpdate(
            update_type="message_callback",
            timestamp=1,
            callback=MaxCallback(
                timestamp=1,
                callback_id="cb-user",
                payload="menu.main",
                user=MaxUser(user_id=456, first_name="Test"),
            ),
        )

        router._send_outbound(
            inbound,
            MaxOutboundMessage(
                text="Меню",
                buttons=[MaxOutboundButton(title="Старт", action="/start")],
            ),
        )

        router.max_client.answer_callback.assert_called_once()
        callback_kwargs = router.max_client.answer_callback.call_args.kwargs
        self.assertEqual(callback_kwargs["new_text"], "Меню")
        router.max_client.delete_message.assert_not_called()
        router.max_client.send_message.assert_not_called()
        router.bot_message_cursor_store.set.assert_not_called()

    def test_callback_without_top_chat_id_ignores_embedded_recipient_chat(self) -> None:
        router = self._build_router()

        inbound = MaxUpdate(
            update_type="message_callback",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=456),
                timestamp=1,
                body=MaxMessageBody(mid="m1", seq=1, text="old"),
                sender=MaxUser(user_id=456, first_name="Test"),
            ),
            callback=MaxCallback(
                timestamp=1,
                callback_id="cb-user",
                payload="menu.my_lates",
                user=MaxUser(user_id=456, first_name="Test"),
            ),
        )

        router._send_outbound(
            inbound,
            MaxOutboundMessage(
                text="Твои случаи",
                buttons=[MaxOutboundButton(title="Назад", action="employee.reasons")],
            ),
        )

        router.max_client.answer_callback.assert_called_once()
        callback_kwargs = router.max_client.answer_callback.call_args.kwargs
        self.assertEqual(callback_kwargs["new_text"], "Твои случаи")
        router.max_client.send_message.assert_not_called()
        router.max_client.delete_message.assert_not_called()
        router.bot_message_cursor_store.set.assert_called_once_with(
            conversation_key="user:456",
            chat_id="",
            user_id="456",
            message_id="m1",
        )

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

    def test_orphaned_late_notice_reason_callback_restarts_flow(self) -> None:
        router = MaxWebhookRouter()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = False
        router.role_resolver.resolve_role = MagicMock(return_value="employee")
        router._start_running_late_flow = MagicMock(
            return_value=MaxWebhookResponse(
                ok=True,
                role="employee",
                menu=[],
                outbound=MaxOutboundMessage(text="Выбери руководителя", buttons=[]),
                active_flow="running_late",
            )
        )

        payload = MaxUpdate(
            update_type="message_callback",
            timestamp=1,
            chat_id=777,
            callback=MaxCallback(
                timestamp=1,
                callback_id="cb-vacation",
                payload="late_notice.reason:vacation",
                user=MaxUser(user_id=456, first_name="Test"),
            ),
        )

        response = router.handle_event(payload)

        router._start_running_late_flow.assert_called_once_with("employee", "456")
        self.assertEqual(response.outbound.text, "Выбери руководителя")


if __name__ == "__main__":
    unittest.main()
