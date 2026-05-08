from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.bot.router import MaxWebhookRouter
from app.domain.dialog_state import UserDialogState
from app.domain.enums import DialogFlow
from app.services.dialog_state import dialog_state_store
from app.schemas.max import MaxCallback, MaxMessage, MaxMessageBody, MaxRecipient, MaxUpdate, MaxUser


class MainMenuResetTests(unittest.TestCase):
    def tearDown(self) -> None:
        dialog_state_store.reset("203302812")

    def test_main_menu_resets_active_flow_before_any_dialog_handler(self) -> None:
        router = MaxWebhookRouter()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = False

        dialog_state_store.set(
            "203302812",
            UserDialogState(
                flow=DialogFlow.SUBSTITUTION.value,
                step="choose_target",
                data={"target_manager_user_id": "mgr-1"},
            ),
        )

        payload = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=203302812),
                timestamp=1,
                body=MaxMessageBody(mid="m1", seq=1, text="Главное меню"),
                sender=MaxUser(user_id=203302812, first_name="Test"),
            ),
        )

        response = router.handle_event(payload)

        self.assertEqual(response.outbound.text, "Главное меню готово.")
        self.assertIsNone(dialog_state_store.get("203302812"))

    def test_start_command_opens_main_menu(self) -> None:
        router = MaxWebhookRouter()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = False

        payload = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=203302812),
                timestamp=1,
                body=MaxMessageBody(mid="m2", seq=2, text="/start"),
                sender=MaxUser(user_id=203302812, first_name="Test"),
            ),
        )

        response = router.handle_event(payload)

        self.assertEqual(response.outbound.text, "Главное меню готово.")
        self.assertIsNone(dialog_state_store.get("203302812"))

    def test_main_menu_alias_opens_main_menu(self) -> None:
        router = MaxWebhookRouter()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = False

        payload = MaxUpdate(
            update_type="message_callback",
            timestamp=1,
            chat_id=987,
            callback=MaxCallback(
                timestamp=1,
                callback_id="cb-main",
                payload="menu_main",
                user=MaxUser(user_id=203302812, first_name="Test"),
            ),
        )

        response = router.handle_event(payload)

        self.assertEqual(response.outbound.text, "Главное меню готово.")
        self.assertIsNone(dialog_state_store.get("203302812"))

    def test_main_menu_reset_does_not_touch_other_user_state(self) -> None:
        router = MaxWebhookRouter()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = False

        dialog_state_store.set(
            "203302812",
            UserDialogState(
                flow=DialogFlow.SUBSTITUTION.value,
                step="choose_target",
                data={"target_manager_user_id": "mgr-1"},
            ),
        )
        dialog_state_store.set(
            "203302813",
            UserDialogState(
                flow=DialogFlow.ATTENDANCE_REASON.value,
                step="choose_reason",
                data={"case_id": "case-1"},
            ),
        )

        payload = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=203302812),
                timestamp=1,
                body=MaxMessageBody(mid="m3", seq=3, text="Главное меню"),
                sender=MaxUser(user_id=203302812, first_name="Test"),
            ),
        )

        response = router.handle_event(payload)

        self.assertEqual(response.outbound.text, "Главное меню готово.")
        self.assertIsNone(dialog_state_store.get("203302812"))
        self.assertIsNotNone(dialog_state_store.get("203302813"))


if __name__ == "__main__":
    unittest.main()
