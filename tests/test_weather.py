from __future__ import annotations

from datetime import UTC, datetime, timedelta
import unittest
from unittest.mock import MagicMock
from unittest.mock import patch

from app.bot.actions import BotAction
from app.bot.buttons import main_menu_buttons
from app.bot.router import MaxWebhookRouter
from app.config import Settings
from app.domain.dialog_state import UserDialogState
from app.domain.enums import DialogFlow
from app.schemas.max import MaxAttachment, MaxCallback, MaxMessage, MaxMessageBody, MaxRecipient, MaxUpdate, MaxUser
from app.services.dialog_state import dialog_state_store
from app.services.weather import DailyWeather, WeatherService


class _FakeWeatherLocationRepository:
    def __init__(self) -> None:
        self.rows = {}

    def get(self, user_id: str):
        return self.rows.get(str(user_id))

    def save(self, user_id: str, latitude: str, longitude: str, ttl_seconds: int = 86400) -> None:
        self.rows[str(user_id)] = (
            latitude,
            longitude,
            datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=ttl_seconds),
        )


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
        router.weather_service.forecast_for_user.return_value = "Погода на 7 дней:\nСегодня: ясно."
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

    def test_weather_action_asks_for_location_without_cached_location(self) -> None:
        dialog_state_store.reset("124")
        router = MaxWebhookRouter()
        router.role_resolver.resolve_role = MagicMock(return_value="employee")
        router.weather_service = MagicMock()
        router.weather_service.forecast_for_user.return_value = None
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
                    user=MaxUser(user_id=124, first_name="Test"),
                ),
            )
        )

        self.assertIn("Отправь свою геолокацию", response.outbound.text)
        self.assertEqual(response.outbound.buttons[0].button_type, "request_geo_location")

    def test_weather_location_is_saved_and_used(self) -> None:
        dialog_state_store.reset("125")
        router = MaxWebhookRouter()
        router.role_resolver.resolve_role = MagicMock(return_value="employee")
        router.weather_service = MagicMock()
        router.weather_service.forecast_for_user.return_value = None
        router.weather_service.save_user_location.return_value = "Погода на 7 дней"
        router.max_client = MagicMock()
        router.max_client.is_configured.return_value = False
        router._touch_user_activity = MagicMock()

        router.handle_event(
            MaxUpdate(
                update_type="message_callback",
                timestamp=1,
                chat_id=987,
                callback=MaxCallback(
                    timestamp=1,
                    callback_id="cb-weather",
                    payload=BotAction.MENU_WEATHER,
                    user=MaxUser(user_id=125, first_name="Test"),
                ),
            )
        )
        response = router.handle_event(
            MaxUpdate(
                update_type="message_created",
                timestamp=2,
                message=MaxMessage(
                    recipient=MaxRecipient(chat_id=987, chat_type="dialog", user_id=125),
                    timestamp=2,
                    body=MaxMessageBody(
                        mid="m-weather",
                        seq=2,
                        attachments=[MaxAttachment(type="location", latitude=55.75, longitude=37.62)],
                    ),
                    sender=MaxUser(user_id=125, first_name="Test"),
                ),
            )
        )

        self.assertIn("Погода на 7 дней", response.outbound.text)
        router.weather_service.save_user_location.assert_called_once_with("125", 55.75, 37.62)

    def test_user_location_is_loaded_after_service_restart(self) -> None:
        repository = _FakeWeatherLocationRepository()
        first = WeatherService(location_repository=repository)
        second = WeatherService(location_repository=repository)

        with patch.object(WeatherService, "_load_forecast", return_value=[]):
            first.save_user_location("128", 55.75, 37.62)
            text = second.forecast_for_user("128")

        self.assertEqual(text, "Погода временно недоступна. Попробуй позже.")

    def test_forecast_for_same_location_is_cached(self) -> None:
        service = WeatherService(location_repository=_FakeWeatherLocationRepository())
        days = [
            DailyWeather(
                date="2026-07-30",
                code=0,
                temp_min=20,
                temp_max=25,
                feels_max=24,
                precipitation=0,
                wind_max=5,
                uv_max=3,
            )
        ]

        with patch.object(service, "_load_forecast", return_value=days) as load_forecast:
            first = service.forecast_text("55.75", "37.62")
            second = service.forecast_text("55.75", "37.62")

        self.assertEqual(first, second)
        load_forecast.assert_called_once()

    def test_weather_action_resets_other_active_flow(self) -> None:
        dialog_state_store.reset("126")
        dialog_state_store.set(
            "126",
            UserDialogState(flow=DialogFlow.SUBSTITUTION.value, step="reason", data={}),
        )
        router = MaxWebhookRouter()
        router.role_resolver.resolve_role = MagicMock(return_value="employee")
        router.weather_service = MagicMock()
        router.weather_service.forecast_for_user.return_value = "Погода на 7 дней:\nСегодня: ясно."
        router.substitution_flow.handle_input = MagicMock()
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
                    callback_id="cb-weather-active",
                    payload=BotAction.MENU_WEATHER,
                    user=MaxUser(user_id=126, first_name="Test"),
                ),
            )
        )

        self.assertIn("Погода на 7 дней", response.outbound.text)
        router.substitution_flow.handle_input.assert_not_called()
        self.assertIsNone(dialog_state_store.get("126"))

    def test_main_menu_resets_weather_location_flow(self) -> None:
        dialog_state_store.reset("127")
        dialog_state_store.set(
            "127",
            UserDialogState(flow=DialogFlow.WEATHER_LOCATION.value, step="await_location", data={}),
        )
        router = MaxWebhookRouter()
        router.role_resolver.resolve_role = MagicMock(return_value="employee")
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
                    callback_id="cb-main-active-weather",
                    payload=BotAction.MAIN_MENU,
                    user=MaxUser(user_id=127, first_name="Test"),
                ),
            )
        )

        self.assertIn("Главное меню", response.outbound.text)
        self.assertIsNone(dialog_state_store.get("127"))

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
