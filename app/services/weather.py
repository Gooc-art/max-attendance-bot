from __future__ import annotations

import json
from dataclasses import dataclass
from time import monotonic
from urllib.parse import urlencode
from urllib.request import urlopen

from app.config import get_settings


@dataclass(frozen=True)
class DailyWeather:
    date: str
    code: int
    temp_min: float
    temp_max: float
    feels_max: float
    precipitation: float
    wind_max: float
    uv_max: float


class WeatherService:
    def __init__(self) -> None:
        self._cache: tuple[float, str] | None = None
        self._user_locations: dict[str, tuple[float, str, str]] = {}

    def forecast_text(self, latitude: str | None = None, longitude: str | None = None) -> str:
        settings = get_settings()
        use_default_location = latitude is None and longitude is None
        latitude = latitude or settings.weather_latitude
        longitude = longitude or settings.weather_longitude
        if not latitude or not longitude:
            return "Погода пока не настроена. Нужно один раз указать город или координаты офиса."

        now = monotonic()
        if use_default_location and self._cache and self._cache[0] > now:
            return self._cache[1]

        try:
            days = self._load_forecast(latitude, longitude)
        except Exception:
            return "Погода временно недоступна. Попробуй позже."

        text = self._format_forecast(days)
        if use_default_location:
            self._cache = (now + settings.weather_cache_ttl_seconds, text)
        return text

    def forecast_for_user(self, user_id: str) -> str | None:
        location = self._user_location(user_id)
        if location is None:
            return None
        return self.forecast_text(location[0], location[1])

    def save_user_location(self, user_id: str, latitude: float, longitude: float) -> str:
        self._user_locations[str(user_id)] = (monotonic() + 86400, str(latitude), str(longitude))
        return self.forecast_text(str(latitude), str(longitude))

    def _user_location(self, user_id: str) -> tuple[str, str] | None:
        location = self._user_locations.get(str(user_id))
        if location is None:
            return None
        expires_at, latitude, longitude = location
        if expires_at <= monotonic():
            self._user_locations.pop(str(user_id), None)
            return None
        return latitude, longitude

    def _load_forecast(self, latitude: str, longitude: str) -> list[DailyWeather]:
        query = urlencode(
            {
                "latitude": latitude,
                "longitude": longitude,
                "forecast_days": "7",
                "timezone": "auto",
                "daily": ",".join(
                    [
                        "weather_code",
                        "temperature_2m_max",
                        "temperature_2m_min",
                        "apparent_temperature_max",
                        "precipitation_sum",
                        "wind_speed_10m_max",
                        "uv_index_max",
                    ]
                ),
            }
        )
        with urlopen(f"https://api.open-meteo.com/v1/forecast?{query}", timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))

        daily = payload.get("daily") or {}
        dates = daily.get("time") or []
        return [
            DailyWeather(
                date=dates[index],
                code=int((daily.get("weather_code") or [0])[index] or 0),
                temp_min=float((daily.get("temperature_2m_min") or [0])[index] or 0),
                temp_max=float((daily.get("temperature_2m_max") or [0])[index] or 0),
                feels_max=float((daily.get("apparent_temperature_max") or [0])[index] or 0),
                precipitation=float((daily.get("precipitation_sum") or [0])[index] or 0),
                wind_max=float((daily.get("wind_speed_10m_max") or [0])[index] or 0),
                uv_max=float((daily.get("uv_index_max") or [0])[index] or 0),
            )
            for index in range(min(7, len(dates)))
        ]

    @classmethod
    def _format_forecast(cls, days: list[DailyWeather]) -> str:
        if not days:
            return "Погода временно недоступна. Попробуй позже."

        lines = ["Погода на 7 дней:"]
        for index, day in enumerate(days):
            label = "Сегодня" if index == 0 else day.date
            lines.append(
                "{label}: {summary}, {temp_min:.0f}..{temp_max:.0f}C, ощущается до {feels:.0f}C. {advice}".format(
                    label=label,
                    summary=cls._summary(day.code),
                    temp_min=day.temp_min,
                    temp_max=day.temp_max,
                    feels=day.feels_max,
                    advice=cls._clothes_advice(day),
                )
            )
        return "\n".join(lines)

    @staticmethod
    def _summary(code: int) -> str:
        if code in {0, 1}:
            return "ясно"
        if code in {2, 3, 45, 48}:
            return "облачно"
        if 51 <= code <= 67 or 80 <= code <= 82:
            return "дождь"
        if 71 <= code <= 77 or 85 <= code <= 86:
            return "снег"
        if 95 <= code <= 99:
            return "гроза"
        return "переменно"

    @classmethod
    def _clothes_advice(cls, day: DailyWeather) -> str:
        parts = []
        feels = day.feels_max
        if feels < -5:
            parts.append("Теплая куртка, шапка, перчатки")
        elif feels < 8:
            parts.append("Теплая куртка")
        elif feels < 16:
            parts.append("Легкая куртка или худи")
        elif feels < 24:
            parts.append("Легкий слой")
        else:
            parts.append("Легкая одежда")

        if cls._is_wet(day):
            parts.append("зонт")
        if day.wind_max >= 35:
            parts.append("ветрозащитный слой")
        if day.uv_max >= 6:
            parts.append("очки/крем от солнца")
        return "; ".join(parts) + "."

    @staticmethod
    def _is_wet(day: DailyWeather) -> bool:
        return day.precipitation >= 1 or 51 <= day.code <= 77 or 80 <= day.code <= 86 or 95 <= day.code <= 99
