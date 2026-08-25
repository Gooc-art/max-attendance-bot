from __future__ import annotations

import unittest
from types import SimpleNamespace
from threading import Event
from unittest.mock import MagicMock

from app.bot.router import MaxWebhookRouter
from app.integrations.max.client import INVISIBLE_MESSAGE_TEXT
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
        router.runtime_marker_repository = MagicMock()
        router.runtime_marker_repository.claim.return_value = True
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
                body=MaxMessageBody(mid="m1", seq=1, text="hello"),
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
        router.runtime_marker_repository.complete.assert_called_once()
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

    def test_duplicate_visible_outbound_is_suppressed_across_events(self) -> None:
        router = self._build_router()
        router.runtime_marker_repository.claim.side_effect = [True, False]
        router.max_client.send_message.return_value = {"mid": "bot-1"}
        outbound = MaxOutboundMessage(
            text="Главное меню готово.",
            buttons=[MaxOutboundButton(title="Отчеты", action="menu.reports")],
        )
        first = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=1,
                body=MaxMessageBody(mid="m1", seq=1, text="hello"),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
        )
        second = MaxUpdate(
            update_type="message_created",
            timestamp=2,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=2,
                body=MaxMessageBody(mid="m2", seq=2, text="hello again"),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        router._send_outbound(first, outbound)
        router._send_outbound(second, outbound)

        router.max_client.send_message.assert_called_once()

    def test_start_navigation_refresh_is_not_suppressed_as_duplicate(self) -> None:
        router = self._build_router()
        router.max_client.send_message.side_effect = [{"mid": "bot-1"}, {"mid": "bot-2"}]
        outbound = MaxOutboundMessage(
            text="Главное меню готово.",
            buttons=[MaxOutboundButton(title="Отчеты", action="menu.reports")],
        )
        bot_started = MaxUpdate(
            update_type="bot_started",
            timestamp=1,
            chat_id=987,
            user=MaxUser(user_id=123, first_name="Test"),
        )
        start_message = MaxUpdate(
            update_type="message_created",
            timestamp=2,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=2,
                body=MaxMessageBody(mid="m2", seq=2, text="/start"),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        router._send_outbound(bot_started, outbound)
        router._send_outbound(start_message, outbound)

        self.assertEqual(router.max_client.send_message.call_count, 2)
        router.runtime_marker_repository.claim.assert_not_called()

    def test_start_sends_fresh_menu_when_previous_menu_exists(self) -> None:
        router = self._build_router()
        router.bot_message_cursor_store.get.return_value = "bot-prev"
        router.max_client.send_message.return_value = {"mid": "bot-next"}
        router._queue_delete_message_ids = MagicMock()

        inbound = MaxUpdate(
            update_type="bot_started",
            timestamp=1,
            chat_id=987,
            user=MaxUser(user_id=123, first_name="Test"),
        )

        router._send_outbound(inbound, MaxOutboundMessage(text="Главное меню готово."))

        router.max_client.edit_message.assert_not_called()
        router.max_client.send_message.assert_called_once_with(
            chat_id=987,
            text="Главное меню готово.",
            buttons=[],
        )
        router._queue_delete_message_ids.assert_called_once_with(["bot-prev"])
        router.bot_message_cursor_store.set.assert_any_call(
            conversation_key="chat:987",
            chat_id="987",
            user_id="123",
            message_id="bot-next",
        )

    def test_async_callback_outbound_returns_before_max_send(self) -> None:
        router = self._build_router()
        router.async_callback_outbound = True
        sent = Event()

        def answer_callback(**kwargs):
            sent.set()
            return {"status": "ok"}

        router.max_client.answer_callback.side_effect = answer_callback
        inbound = MaxUpdate(
            update_type="message_callback",
            timestamp=1,
            chat_id=987,
            callback=MaxCallback(
                timestamp=1,
                callback_id="cb-async",
                payload="menu.main",
                user=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        router._send_outbound(inbound, MaxOutboundMessage(text="Hello"))

        self.assertTrue(sent.wait(1))
        router.max_client.answer_callback.assert_called_once()

    def test_message_updates_fallback_to_user_id_when_chat_id_fails(self) -> None:
        router = self._build_router()
        router.max_client.send_message.side_effect = [RuntimeError("chat failed"), {"status": "ok", "mid": "bot-2"}]

        inbound = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=1,
                body=MaxMessageBody(mid="m1", seq=1, text="hello"),
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
        router.runtime_marker_repository.release.assert_called_once()
        router.runtime_marker_repository.complete.assert_called_once()
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
                body=MaxMessageBody(mid="m1", seq=1, text="hello"),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        router._send_outbound(inbound, MaxOutboundMessage(text="Hello"))

        router.max_client.delete_message.assert_not_called()
        router.max_client.soft_clear_message.assert_not_called()
        router.max_client.send_message.assert_called_once()

    def test_real_cursor_store_bulk_methods_are_used(self) -> None:
        class BulkCursorStore:
            def __init__(self) -> None:
                self.saved = None

            def get_many(self, keys):
                return {"chat:987": "bot-prev", "user:123": "bot-prev"}

            def set_many(self, keys, chat_id, user_id, message_id):
                self.saved = (keys, chat_id, user_id, message_id)

            def reset_many(self, keys):
                self.saved = (keys, "", "", "")

        router = self._build_router()
        cursor = BulkCursorStore()
        router.bot_message_cursor_store = cursor
        router.max_client.send_message.return_value = {"mid": "bot-next"}

        inbound = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=1,
                body=MaxMessageBody(mid="m1", seq=1, text="hello"),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        router._send_outbound(inbound, MaxOutboundMessage(text="Hello"))

        router.max_client.edit_message.assert_not_called()
        router.max_client.send_message.assert_called_once()
        self.assertEqual(cursor.saved, (["chat:987", "user:123"], "987", "123", "bot-next"))

    def test_previous_bot_message_delete_uses_cursor_history(self) -> None:
        class HistoryCursorStore:
            def get_many(self, keys):
                return {
                    "chat:987": "bot-newer\nbot-older",
                    "user:123": "bot-newer\nbot-older",
                }

            def set_many(self, keys, chat_id, user_id, message_id):
                return message_id

        router = self._build_router()
        router.bot_message_cursor_store = HistoryCursorStore()
        router.max_client.send_message.return_value = {"mid": "bot-next"}
        router._queue_delete_message_ids = MagicMock()

        inbound = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=1,
                body=MaxMessageBody(mid="m1", seq=1, text="hello"),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        router._send_outbound(inbound, MaxOutboundMessage(text="Hello"))

        router.max_client.edit_message.assert_not_called()
        router.max_client.send_message.assert_called_once()
        router._queue_delete_message_ids.assert_called_once_with(["bot-newer", "bot-older"])

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
        self.assertEqual(callback_kwargs["notification"], INVISIBLE_MESSAGE_TEXT)
        router.max_client.edit_message.assert_called_once_with(
            "bot-card",
            text="Hello",
            buttons=[MaxOutboundButton(title="Старт", action="/start")],
        )
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

    def test_callback_update_deletes_previous_cursor_message(self) -> None:
        router = self._build_router()
        router.bot_message_cursor_store.get.return_value = "bot-prev"
        router._queue_delete_message_ids = MagicMock()

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

        router._send_outbound(inbound, MaxOutboundMessage(text="Главное меню готово."))

        router.max_client.edit_message.assert_called_once()
        router._queue_delete_message_ids.assert_called_once_with(["bot-prev"])

    def test_handle_event_answers_callback_once_with_final_message(self) -> None:
        router = self._build_router()
        router.role_resolver.resolve_role = MagicMock(return_value="employee")
        router.user_bot_activity_repository.touch = MagicMock()
        router.max_client.send_message.return_value = {"mid": "bot-next"}
        router._queue_delete_message_ids = MagicMock()

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
            callback=MaxCallback(
                timestamp=1,
                callback_id="cb-1",
                payload="menu.main",
                user=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        response = router.handle_event(inbound)

        self.assertEqual(response.outbound.text, "Главное меню готово.")
        router.max_client.answer_callback.assert_called_once_with(
            callback_id="cb-1",
            notification=INVISIBLE_MESSAGE_TEXT,
        )
        router.max_client.delete_message.assert_called_once_with("bot-card")
        router.max_client.edit_message.assert_not_called()
        router.max_client.send_message.assert_called_once_with(
            chat_id=987,
            text="Главное меню готово.",
            buttons=response.outbound.buttons,
        )
        router._queue_delete_message_ids.assert_not_called()

    def test_office_seal_ack_callback_deletes_callback_message(self) -> None:
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
            callback=MaxCallback(
                timestamp=1,
                callback_id="cb-ack",
                payload="office_seal.reminder_ack",
                user=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        router._send_outbound(inbound, MaxOutboundMessage(text="Принято, спасибо."))

        router.max_client.answer_callback.assert_called_once_with(
            callback_id="cb-ack",
            notification="Принято, спасибо.",
        )
        router.max_client.delete_message.assert_called_once_with("bot-card")
        router.max_client.edit_message.assert_not_called()
        router.max_client.send_message.assert_not_called()
        router.bot_message_cursor_store.set.assert_not_called()

    def test_office_seal_ack_soft_clears_callback_message_when_delete_fails(self) -> None:
        router = self._build_router()
        router.max_client.delete_message.side_effect = RuntimeError("delete forbidden")

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
            callback=MaxCallback(
                timestamp=1,
                callback_id="cb-ack",
                payload="office_seal.reminder_ack",
                user=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        router._send_outbound(inbound, MaxOutboundMessage(text="Принято, спасибо."))

        router.max_client.delete_message.assert_called_once_with("bot-card")
        router.max_client.soft_clear_message.assert_called_once_with("bot-card")
        router.max_client.edit_message.assert_not_called()
        router.max_client.send_message.assert_not_called()

    def test_office_seal_ack_deletes_callback_message_when_answer_callback_fails(self) -> None:
        router = self._build_router()
        router.max_client.answer_callback.side_effect = RuntimeError("answer failed")
        router.max_client.send_message.return_value = {"status": "ok", "mid": "bot-3"}

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
            callback=MaxCallback(
                timestamp=1,
                callback_id="cb-ack",
                payload="office_seal.reminder_ack",
                user=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        router._send_outbound(inbound, MaxOutboundMessage(text="Принято, спасибо."))

        router.max_client.answer_callback.assert_called_once_with(
            callback_id="cb-ack",
            notification="Принято, спасибо.",
        )
        router.max_client.delete_message.assert_called_once_with("bot-card")
        router.max_client.send_message.assert_called_once()

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

    def test_main_menu_callback_deletes_old_menu_before_fresh_visible_menu(self) -> None:
        router = self._build_router()
        router.max_client.send_message.return_value = {"mid": "bot-next"}
        router._queue_delete_message_ids = MagicMock()

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

        router.max_client.answer_callback.assert_called_once()
        answer_kwargs = router.max_client.answer_callback.call_args.kwargs
        self.assertEqual(answer_kwargs["callback_id"], "cb-main")
        self.assertEqual(answer_kwargs["notification"], INVISIBLE_MESSAGE_TEXT)
        router.max_client.delete_message.assert_called_once_with("bot-main-card")
        router.max_client.edit_message.assert_not_called()
        router.max_client.send_message.assert_called_once_with(
            chat_id=987,
            text="Главное меню готово.",
            buttons=[MaxOutboundButton(title="Старт", action="/start")],
        )
        calls = [item[0] for item in router.max_client.mock_calls]
        self.assertLess(calls.index("delete_message"), calls.index("send_message"))
        router._queue_delete_message_ids.assert_not_called()
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

    def test_main_menu_callback_without_top_level_chat_edits_current_menu(self) -> None:
        router = self._build_router()
        router._queue_delete_message_ids = MagicMock()

        inbound = MaxUpdate(
            update_type="message_callback",
            timestamp=1,
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

        router.max_client.answer_callback.assert_called_once_with(
            callback_id="cb-main",
            notification=INVISIBLE_MESSAGE_TEXT,
        )
        router.max_client.edit_message.assert_called_once_with(
            "bot-main-card",
            text="Главное меню готово.",
            buttons=[MaxOutboundButton(title="Старт", action="/start")],
        )
        router.max_client.send_message.assert_not_called()
        router._queue_delete_message_ids.assert_not_called()

    def test_duplicate_main_menu_callback_does_not_send_visible_duplicate(self) -> None:
        router = self._build_router()
        router.runtime_marker_repository.claim.side_effect = [True, True, True, False]
        router.max_client.send_message.return_value = {"mid": "bot-next"}
        router._queue_delete_message_ids = MagicMock()
        outbound = MaxOutboundMessage(
            text="Главное меню готово.",
            buttons=[MaxOutboundButton(title="Старт", action="/start")],
        )
        first = MaxUpdate(
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
                callback_id="cb-main-1",
                payload="menu.main",
                user=MaxUser(user_id=123, first_name="Test"),
            ),
        )
        second = first.model_copy(
            update={
                "timestamp": 2,
                "callback": MaxCallback(
                    timestamp=2,
                    callback_id="cb-main-2",
                    payload="menu.main",
                    user=MaxUser(user_id=123, first_name="Test"),
                ),
            }
        )

        router._send_outbound(first, outbound)
        router._send_outbound(second, outbound)

        router.max_client.delete_message.assert_called_once_with("bot-main-card")
        router.max_client.edit_message.assert_not_called()
        router.max_client.send_message.assert_called_once()
        self.assertEqual(router.max_client.answer_callback.call_count, 2)
        router._queue_delete_message_ids.assert_not_called()

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

    def test_previous_bot_message_is_queued_for_delete_after_sending_new_one(self) -> None:
        router = self._build_router()
        router.bot_message_cursor_store.get.return_value = "bot-prev"
        router.max_client.send_message.return_value = {"mid": "bot-next"}
        router._queue_delete_message_ids = MagicMock()

        inbound = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=1,
                body=MaxMessageBody(mid="m1", seq=1, text="hello"),
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

        router.max_client.edit_message.assert_not_called()
        router.max_client.send_message.assert_called_once()
        router._queue_delete_message_ids.assert_called_once_with(["bot-prev"])
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
        router.max_client.delete_message.side_effect = RuntimeError("delete forbidden")

        router._delete_message_ids(["bot-prev"])

        router.max_client.delete_message.assert_called_once_with("bot-prev")
        router.max_client.soft_clear_message.assert_called_once_with("bot-prev")

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

    def test_incoming_dedup_key_requires_scoped_participant(self) -> None:
        router = MaxWebhookRouter()

        key = router.incoming_dedup_key(MaxUpdate(update_type="bot_started", timestamp=1))

        self.assertEqual(key, "")

    def test_start_events_share_incoming_dedup_key(self) -> None:
        router = MaxWebhookRouter()

        bot_started = MaxUpdate(
            update_type="bot_started",
            timestamp=1000,
            chat_id=987,
            user=MaxUser(user_id=123, first_name="Test"),
        )
        start_message = MaxUpdate(
            update_type="message_created",
            timestamp=1005,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=1005,
                body=MaxMessageBody(mid="m-start", seq=1, text="/start"),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        self.assertEqual(router.incoming_dedup_key(bot_started), router.incoming_dedup_key(start_message))

    def test_callback_id_is_used_before_action_dedup(self) -> None:
        router = MaxWebhookRouter()

        first = MaxUpdate(
            update_type="message_callback",
            timestamp=1000,
            chat_id=987,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=1000,
                body=MaxMessageBody(mid="bot-card", seq=1, text="old"),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
            callback=MaxCallback(
                timestamp=1000,
                callback_id="cb-1",
                payload="menu.approvals",
                user=MaxUser(user_id=123, first_name="Test"),
            ),
        )
        duplicate = first.model_copy(
            update={
                "timestamp": 1001,
                "callback": MaxCallback(
                    timestamp=1001,
                    callback_id="cb-2",
                    payload="menu.approvals",
                    user=MaxUser(user_id=123, first_name="Test"),
                ),
            },
        )
        self.assertNotEqual(router.incoming_dedup_key(first), router.incoming_dedup_key(duplicate))

    def test_callback_without_id_falls_back_to_action_dedup(self) -> None:
        router = MaxWebhookRouter()

        first = MaxUpdate(
            update_type="message_callback",
            timestamp=1000,
            chat_id=987,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=1000,
                body=MaxMessageBody(mid="bot-card", seq=1, text="old"),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
            callback=MaxCallback(
                timestamp=1000,
                callback_id="",
                payload="menu.approvals",
                user=MaxUser(user_id=123, first_name="Test"),
            ),
        )
        duplicate = first.model_copy(
            update={
                "timestamp": 1001,
                "callback": MaxCallback(
                    timestamp=1001,
                    callback_id="",
                    payload="menu.approvals",
                    user=MaxUser(user_id=123, first_name="Test"),
                ),
            },
        )
        later = duplicate.model_copy(update={"timestamp": 1003})

        self.assertEqual(router.incoming_dedup_key(first), router.incoming_dedup_key(duplicate))
        self.assertNotEqual(router.incoming_dedup_key(first), router.incoming_dedup_key(later))

        other_user = duplicate.model_copy(
            update={
                "callback": MaxCallback(
                    timestamp=1001,
                    callback_id="",
                    payload="menu.approvals",
                    user=MaxUser(user_id=456, first_name="Other"),
                ),
            },
        )
        other_message = duplicate.model_copy(
            update={
                "message": MaxMessage(
                    recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                    timestamp=1001,
                    body=MaxMessageBody(mid="other-card", seq=1, text="old"),
                    sender=MaxUser(user_id=123, first_name="Test"),
                ),
            },
        )

        self.assertNotEqual(router.incoming_dedup_key(first), router.incoming_dedup_key(other_user))
        self.assertNotEqual(router.incoming_dedup_key(first), router.incoming_dedup_key(other_message))

    def test_main_menu_callback_without_top_level_chat_edits_current_message(self) -> None:
        router = self._build_router()
        router._queue_delete_message_ids = MagicMock()

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
        self.assertEqual(callback_kwargs["notification"], INVISIBLE_MESSAGE_TEXT)
        router.max_client.edit_message.assert_called_once_with(
            "bot-card",
            text="Меню",
            buttons=[MaxOutboundButton(title="Старт", action="/start")],
        )
        router.max_client.send_message.assert_not_called()
        router._queue_delete_message_ids.assert_not_called()
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

    def test_outgoing_duplicate_marker_skips_send(self) -> None:
        router = self._build_router()
        router.runtime_marker_repository.claim.return_value = False

        inbound = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=1,
                body=MaxMessageBody(mid="m1", seq=1, text="hello"),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        router._send_outbound(inbound, MaxOutboundMessage(text="Hello"))

        router.max_client.send_message.assert_not_called()
        router.runtime_marker_repository.complete.assert_not_called()
        router.bot_message_cursor_store.set.assert_not_called()

    def test_whoami_visible_message_is_not_saved_as_clearable_cursor(self) -> None:
        router = self._build_router()
        router.max_client.send_message.return_value = {"mid": "whoami-mid"}

        inbound = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=1,
                body=MaxMessageBody(mid="m1", seq=1, text="Обо мне"),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
        )

        router._send_outbound(inbound, MaxOutboundMessage(text="Обо мне:\n\nУстройство: Android"))

        router.max_client.send_message.assert_called_once()
        router.bot_message_cursor_store.set.assert_not_called()

    def test_outgoing_marker_released_when_send_fails(self) -> None:
        router = self._build_router()
        router.max_client.send_message.side_effect = RuntimeError("MAX down")

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

        self.assertEqual(router.max_client.send_message.call_count, 2)
        self.assertEqual(router.runtime_marker_repository.release.call_count, 2)
        router.runtime_marker_repository.complete.assert_not_called()

    def test_same_callback_text_with_new_callback_id_is_not_suppressed(self) -> None:
        router = self._build_router()
        claimed = set()

        def claim(marker_key: str, marker_type: str, lease_seconds: int = 120):
            if marker_key in claimed:
                return False
            claimed.add(marker_key)
            return True

        router.runtime_marker_repository.claim.side_effect = claim

        for callback_id in ["cb-1", "cb-2"]:
            inbound = MaxUpdate(
                update_type="message_callback",
                timestamp=1,
                callback=MaxCallback(
                    timestamp=1,
                    callback_id=callback_id,
                    payload="/whoami",
                    user=MaxUser(user_id=123, first_name="Test"),
                ),
            )
            router._send_outbound(inbound, MaxOutboundMessage(text="Обо мне:\n\nУстройство: Android"))

        self.assertEqual(router.max_client.answer_callback.call_count, 2)

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
        self.assertEqual(callback_kwargs["notification"], INVISIBLE_MESSAGE_TEXT)
        router.max_client.edit_message.assert_called_once_with(
            "m1",
            text="Твои случаи",
            buttons=[MaxOutboundButton(title="Назад", action="employee.reasons")],
        )
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

    def test_top_department_stats_groups_all_time_metrics_by_department(self) -> None:
        router = MaxWebhookRouter()
        router.case_repository = MagicMock()
        router.report_service = MagicMock()
        router.report_service.visit_repository.list_all.return_value = [
            SimpleNamespace(
                department_name="Отдел продаж",
                event_date="2026-06-01",
                arrival_status="late",
                arrival_delta_minutes=12,
                departure_status="late",
                total_passes=4,
            ),
            SimpleNamespace(
                department_name="Отдел продаж",
                event_date="2026-06-02",
                arrival_status="on_time",
                arrival_delta_minutes=0,
                departure_status="early",
                total_passes=2,
            ),
            SimpleNamespace(
                department_name="ИТ",
                event_date="2026-06-03",
                arrival_status="late",
                arrival_delta_minutes=7,
                departure_status="",
                total_passes=0,
            ),
        ]
        router.case_repository.list_all.return_value = [
            SimpleNamespace(case_type="absent", department_name="Отдел продаж", event_date="2026-06-04"),
            SimpleNamespace(case_type="late", department_name="Отдел продаж", event_date="2026-06-05"),
            SimpleNamespace(case_type="absent", department_name="ИТ", event_date="2026-06-06"),
        ]

        response = router._top_department_stats("top_manager")

        self.assertIn("Статистика отделов за весь период (2026-06-01 - 2026-06-06)", response.outbound.text)
        self.assertIn("Всего дней учета: 3", response.outbound.text)
        self.assertIn("Опозданий: 2 (19 мин)", response.outbound.text)
        self.assertIn("Неявок: 2", response.outbound.text)
        self.assertIn("Без проходов: 1", response.outbound.text)
        self.assertIn("Отдел продаж: дней 2, опозд. 1 (12 мин), неявки 1, без проходов 0, ушли раньше 1, позже 1", response.outbound.text)
        self.assertIn("ИТ: дней 1, опозд. 1 (7 мин), неявки 1, без проходов 1, ушли раньше 0, позже 0", response.outbound.text)
        self.assertEqual(response.outbound.buttons[0].action, "top.summary")

    def test_office_seal_ack_skips_role_resolver(self) -> None:
        router = self._build_router()
        router.role_resolver.resolve_role = MagicMock(side_effect=AssertionError("slow role lookup"))
        router.user_bot_activity_repository.touch = MagicMock()

        payload = MaxUpdate(
            update_type="message_callback",
            timestamp=1,
            chat_id=777,
            callback=MaxCallback(
                timestamp=1,
                callback_id="cb-ack",
                payload="office_seal.reminder_ack",
                user=MaxUser(user_id=456, first_name="Test"),
            ),
        )

        response = router.handle_event(payload)

        router.role_resolver.resolve_role.assert_not_called()
        router.max_client.answer_callback.assert_called_once_with(
            callback_id="cb-ack",
            notification="Принято, спасибо.",
        )
        router.user_bot_activity_repository.touch.assert_called_once_with(
            user_id="456",
            display_name="Test",
            role="",
            started=False,
        )
        self.assertEqual(response.outbound.text, "Принято, спасибо.")

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
