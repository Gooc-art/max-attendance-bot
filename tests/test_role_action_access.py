from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.bot.actions import BotAction
from app.bot.router import MaxWebhookRouter
from app.schemas.max import MaxCallback, MaxMessage, MaxMessageBody, MaxRecipient, MaxUpdate, MaxUser


class RoleActionAccessTests(unittest.TestCase):
    def _callback(self, action: str) -> MaxUpdate:
        return MaxUpdate(
            update_type="message_callback",
            timestamp=1,
            chat_id=987,
            callback=MaxCallback(
                timestamp=1,
                callback_id="cb-role-access",
                payload=action,
                user=MaxUser(user_id=123, first_name="Test"),
            ),
        )

    def _message(self, text: str) -> MaxUpdate:
        return MaxUpdate(
            update_type="message_created",
            timestamp=1,
            message=MaxMessage(
                recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=123),
                timestamp=1,
                body=MaxMessageBody(mid="m-role-access", seq=1, text=text),
                sender=MaxUser(user_id=123, first_name="Test"),
            ),
        )

    def _router_for_role(self, role: str) -> MaxWebhookRouter:
        router = MaxWebhookRouter()
        router.role_resolver.resolve_role = MagicMock(return_value=role)
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = False
        router._touch_user_activity = MagicMock()
        return router

    def test_employee_cannot_open_structure_by_direct_payload(self) -> None:
        response = self._router_for_role("employee").handle_event(self._callback(BotAction.MENU_STAFF))

        self.assertIn("недоступен", response.outbound.text)

    def test_hr_cannot_open_skud_by_direct_payload(self) -> None:
        response = self._router_for_role("hr").handle_event(self._callback(BotAction.SECURITY_SKUD))

        self.assertIn("недоступен", response.outbound.text)

    def test_hidden_stub_actions_are_not_available_by_direct_payload(self) -> None:
        for role, action in [
            ("security", BotAction.SECURITY_AUDIT),
            ("admin", BotAction.MENU_SETTINGS),
            ("admin", BotAction.MENU_MATCH_ERRORS),
            ("hr", BotAction.MENU_SCHEDULES),
        ]:
            with self.subTest(role=role, action=action):
                response = self._router_for_role(role).handle_event(self._callback(action))
                self.assertIn("недоступен", response.outbound.text)

    def test_weather_is_available_to_every_main_role(self) -> None:
        for role in ["employee", "manager", "security", "hr", "admin", "top_manager"]:
            with self.subTest(role=role):
                router = self._router_for_role(role)
                router.weather_service = MagicMock()
                router.weather_service.forecast_for_user.return_value = "Погода на 7 дней"

                response = router.handle_event(self._callback(BotAction.MENU_WEATHER))

                self.assertIn("Погода на 7 дней", response.outbound.text)

    def test_unknown_callback_is_not_reported_as_stub_button(self) -> None:
        response = self._router_for_role("employee").handle_event(self._callback("unknown.action"))

        self.assertIn("Главное меню обновлено", response.outbound.text)
        self.assertNotIn("заглуш", response.outbound.text)
        self.assertTrue(response.outbound.buttons)

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

    def test_manager_text_analytics_falls_back_to_actual_main_menu(self) -> None:
        response = self._router_for_role("manager").handle_event(self._message("Аналитика"))

        self.assertIn("Не понял команду", response.outbound.text)
        self.assertIn("Команда", {button.title for button in response.outbound.buttons})


if __name__ == "__main__":
    unittest.main()
