from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.bot.actions import BotAction
from app.bot.router import MaxWebhookRouter
from app.domain.dialog_state import UserDialogState
from app.domain.enums import DialogFlow
from app.services.dialog_state import dialog_state_store
from app.schemas.max import MaxCallback, MaxMessage, MaxMessageBody, MaxRecipient, MaxUpdate, MaxUser


class MainMenuResetTests(unittest.TestCase):
    def tearDown(self) -> None:
        dialog_state_store.reset("203302812")

    def _router_for_role(self, role: str) -> MaxWebhookRouter:
        router = MaxWebhookRouter()
        router.role_resolver.resolve_role = MagicMock(return_value=role)
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = False
        router._touch_user_activity = MagicMock()
        return router

    def _message(self, text: str) -> MaxUpdate:
        return MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=203302812),
                timestamp=1,
                body=MaxMessageBody(mid="m-text-fallback", seq=1, text=text),
                sender=MaxUser(user_id=203302812, first_name="Test"),
            ),
        )

    def _callback(self, action: str) -> MaxUpdate:
        return MaxUpdate(
            update_type="message_callback",
            timestamp=1,
            chat_id=987,
            callback=MaxCallback(
                timestamp=1,
                callback_id="cb-menu",
                payload=action,
                user=MaxUser(user_id=203302812, first_name="Test"),
            ),
        )

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

    def test_main_menu_does_not_include_device_detection_link_button(self) -> None:
        router = MaxWebhookRouter()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = False

        payload = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=203302812),
                timestamp=1,
                body=MaxMessageBody(mid="m-device", seq=2, text="/start"),
                sender=MaxUser(user_id=203302812, first_name="Test"),
            ),
        )

        response = router.handle_event(payload)

        buttons = {button.title: button for button in response.outbound.buttons}
        self.assertIn("Обо мне", buttons)
        self.assertNotIn("Определить устройство", buttons)

    def test_start_button_text_opens_main_menu(self) -> None:
        router = MaxWebhookRouter()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = False

        payload = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=203302812),
                timestamp=1,
                body=MaxMessageBody(mid="m4", seq=4, text="Старт"),
                sender=MaxUser(user_id=203302812, first_name="Test"),
            ),
        )

        response = router.handle_event(payload)

        self.assertEqual(response.outbound.text, "Главное меню готово.")
        self.assertIsNone(dialog_state_store.get("203302812"))

    def test_begin_button_text_opens_main_menu(self) -> None:
        router = MaxWebhookRouter()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = False

        payload = MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=203302812),
                timestamp=1,
                body=MaxMessageBody(mid="m5", seq=5, text="Начать"),
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

    def test_my_lates_resets_active_flow_before_dialog_handler(self) -> None:
        router = MaxWebhookRouter()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = False
        router.case_repository.list_for_employee_user = MagicMock(return_value=[])

        dialog_state_store.set(
            "203302812",
            UserDialogState(
                flow=DialogFlow.RUNNING_LATE.value,
                step="choose_reason",
                data={"manager_user_id": "mgr-1"},
            ),
        )

        payload = MaxUpdate(
            update_type="message_callback",
            timestamp=1,
            chat_id=987,
            callback=MaxCallback(
                timestamp=1,
                callback_id="cb-lates",
                payload="menu.my_lates",
                user=MaxUser(user_id=203302812, first_name="Test"),
            ),
        )

        response = router.handle_event(payload)

        self.assertIn("У тебя пока нет зарегистрированных случаев", response.outbound.text)
        self.assertIsNone(dialog_state_store.get("203302812"))

    def test_whoami_resets_active_flow_before_dialog_handler(self) -> None:
        router = MaxWebhookRouter()
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = False
        router.employee_directory_repository.get_by_user_id = MagicMock(return_value=None)
        router.google_directory_service.get_by_user_id = MagicMock(return_value=None)

        dialog_state_store.set(
            "203302812",
            UserDialogState(
                flow=DialogFlow.RUNNING_LATE.value,
                step="choose_reason",
                data={"manager_user_id": "mgr-1"},
            ),
        )

        payload = MaxUpdate(
            update_type="message_callback",
            timestamp=1,
            chat_id=987,
            callback=MaxCallback(
                timestamp=1,
                callback_id="cb-whoami",
                payload=BotAction.WHOAMI,
                user=MaxUser(user_id=203302812, first_name="Test"),
            ),
        )

        response = router.handle_event(payload)

        self.assertIn("Обо мне:", response.outbound.text)
        self.assertIsNone(dialog_state_store.get("203302812"))

    def test_top_manager_text_analytics_opens_top_summary(self) -> None:
        response = self._router_for_role("top_manager").handle_event(self._message("Аналитика"))

        self.assertIn("Аналитика верхнего уровня", response.outbound.text)

    def test_top_manager_text_reports_opens_top_reports(self) -> None:
        response = self._router_for_role("top_manager").handle_event(self._message("Отчеты"))

        self.assertIn("Отчеты верхнего уровня", response.outbound.text)

    def test_role_section_text_fallbacks_open_expected_menus(self) -> None:
        cases = [
            ("manager", "Команда", "Раздел команды"),
            ("security", "СКУД", "СКУД: загрузка"),
            ("hr", "Справочники", "Справочники HR"),
            ("hr", "Процессы", "Процессы HR"),
            ("admin", "Личное", "Личный раздел администратора"),
            ("admin", "Структура", "Структура и справочники"),
            ("admin", "СКУД", "Импорт СКУД"),
            ("admin", "Процессы", "Согласования"),
            ("employee", "Руководство", "руководства"),
        ]
        for role, text, expected in cases:
            with self.subTest(role=role, text=text):
                response = self._router_for_role(role).handle_event(self._message(text))
                self.assertIn(expected, response.outbound.text)

    def test_menu_callback_resets_weather_location_flow(self) -> None:
        router = self._router_for_role("manager")
        dialog_state_store.set(
            "203302812",
            UserDialogState(flow=DialogFlow.WEATHER_LOCATION.value, step="await_location", data={}),
        )

        response = router.handle_event(self._callback(BotAction.MANAGER_MANAGEMENT))

        self.assertIn("Раздел команды", response.outbound.text)
        self.assertIsNone(dialog_state_store.get("203302812"))
        self.assertNotIn("Нужна геолокация", response.outbound.text)

    def test_approval_history_text_opens_approval_history(self) -> None:
        response = self._router_for_role("manager").handle_event(self._message("История согласований"))

        self.assertIn("согласований", response.outbound.text)

    def test_unknown_callback_refreshes_stale_menu(self) -> None:
        router = self._router_for_role("employee")
        payload = MaxUpdate(
            update_type="message_callback",
            timestamp=1,
            chat_id=987,
            callback=MaxCallback(
                timestamp=1,
                callback_id="cb-stale",
                payload="unknown.action",
                user=MaxUser(user_id=203302812, first_name="Test"),
            ),
        )

        response = router.handle_event(payload)

        self.assertIn("Главное меню обновлено", response.outbound.text)
        self.assertTrue(response.outbound.buttons)


if __name__ == "__main__":
    unittest.main()
