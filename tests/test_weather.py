from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.bot.actions import BotAction
from app.bot.buttons import main_menu_buttons
from app.bot.router import MaxWebhookRouter
from app.schemas.max import MaxCallback, MaxUpdate, MaxUser
from app.services.weather import DailyWeather, WeatherService


class WeatherTests(unittest.TestCase):
    def test_weather_button_is_in_every_main_menu(self) -> None:
        for role in ["employee", "manager", "security", "hr", "admin", "top_manager"]:
            with self.subTest(role=role):
                actions = [button.action for button in main_menu_buttons(role)]
                self.assertIn(BotAction.MENU_WEATHER, actions)

    def test_weather_action_returns_forecast(self) -> None:
        router = MaxWebhookRouter()
        router.role_resolver.resolve_role = MagicMock(return_value="employee")
        router.weather_service = MagicMock()
        router.weather_service.forecast_text.return_value = "Погода на 7 дней:\nСегодня: ясно."
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = False
        router._touch_user_activity = MagicMock()

        response = router.handle_event(
            MaxUpdate(
                update_type="message_callback",
                timestamp=1,
                chat_id=987,
                callback=MaxCallback(
                    timestamp=1,
                    callback_id="cb-weather",
                    payload=BotAction.MENU_WEATHER,
                    user=MaxUser(user_id=123, first_name="Test"),
                ),
            )
        )

        self.assertIn("Погода на 7 дней", response.outbound.text)
        self.assertEqual(response.outbound.buttons[0].action, BotAction.MAIN_MENU)

    def test_clothes_advice_mentions_rain_and_wind(self) -> None:
        text = WeatherService._format_forecast(
            [
                DailyWeather(
                    date="2026-07-30",
                    code=61,
                    temp_min=10,
                    temp_max=15,
                    feels_max=12,
                    precipitation=4,
                    wind_max=40,
                    uv_max=2,
                )
            ]
        )

        self.assertIn("Легкая куртка", text)
        self.assertIn("зонт", text)
        self.assertIn("ветрозащитный слой", text)


if __name__ == "__main__":
    unittest.main()
