from __future__ import annotations

import unittest
from unittest.mock import MagicMock
from unittest.mock import patch

from app.bot.actions import BotAction
from app.bot.buttons import main_menu_buttons
from app.bot.router import MaxWebhookRouter
from app.config import Settings
from app.schemas.max import MaxCallback, MaxUpdate, MaxUser
from app.services.weather import DailyWeather, WeatherService


class WeatherTests(unittest.TestCase):
    def test_missing_coordinates_uses_human_message(self) -> None:
        settings = Settings(
            app_name="test",
            app_host="127.0.0.1",
            app_port=8000,
            app_debug=False,
            database_url="sqlite://",
            max_api_base_url="",
            max_api_version="",
            max_bot_token="",
            max_bot_secret="",
            max_bot_webhook_url="",
            max_api_timeout_seconds=3,
            max_delete_previous_message=True,
            polling_marker_file="",
            polling_timeout_seconds=1,
            polling_limit=100,
            polling_idle_sleep_seconds=1,
            polling_error_sleep_seconds=5,
            google_service_account_file="",
            google_sheets_spreadsheet_id="",
            google_sheets_employee_range="",
            google_sheets_schedule_range="",
            google_sheets_cache_ttl_seconds=300,
            office_seal_company_timezone="Europe/Amsterdam",
            office_seal_window_start="18:00",
            office_seal_window_end="22:00",
            office_seal_photo_dir="",
            public_base_url="",
            weather_latitude="",
            weather_longitude="",
            weather_cache_ttl_seconds=3600,
        )

        with patch("app.services.weather.get_settings", return_value=settings):
            text = WeatherService().forecast_text()

        self.assertIn("Погода пока не настроена", text)
        self.assertNotIn("WEATHER_", text)

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
