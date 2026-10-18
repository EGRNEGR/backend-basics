import math
from typing import Any

from processing.errors import (
    ApiNotFoundError,
    CityNotFoundError,
    InvalidApiResponseError,
)

from clients.http import get_json

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WEATHER_DESCRIPTIONS = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    56: "light freezing drizzle",
    57: "dense freezing drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "heavy freezing rain",
    71: "slight snow",
    73: "moderate snow",
    75: "heavy snow",
    77: "snow grains",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    85: "slight snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def get_weather(city: str) -> dict[str, float | int | str]:
    city_name = city.strip()
    if not city_name:
        raise CityNotFoundError("название города не может быть пустым")

    try:
        geocoding = get_json(
            GEOCODING_URL,
            params={"name": city_name, "count": 1, "language": "en", "format": "json"},
        )
    except ApiNotFoundError as error:
        raise CityNotFoundError(f"город «{city_name}» не найден") from error

    results = geocoding.get("results", [])
    if not isinstance(results, list):
        raise InvalidApiResponseError("в ответе геокодера отсутствует список results")
    if not results:
        raise CityNotFoundError(f"город «{city_name}» не найден")

    location = results[0]
    if not isinstance(location, dict):
        raise InvalidApiResponseError("некорректная запись города в ответе геокодера")
    latitude = location.get("latitude")
    longitude = location.get("longitude")
    if (
        not _is_number(latitude)
        or not _is_number(longitude)
        or not math.isfinite(float(latitude))
        or not math.isfinite(float(longitude))
    ):
        raise InvalidApiResponseError("координаты города отсутствуют или некорректны")

    forecast = get_json(
        FORECAST_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,weather_code",
            "timezone": "auto",
        },
    )
    current = forecast.get("current")
    if not isinstance(current, dict):
        raise InvalidApiResponseError("в прогнозе отсутствует объект current")

    temperature = current.get("temperature_2m")
    weather_code = current.get("weather_code")
    if (
        not _is_number(temperature)
        or not math.isfinite(float(temperature))
        or not isinstance(weather_code, int)
        or isinstance(weather_code, bool)
    ):
        raise InvalidApiResponseError(
            "температура или код погоды отсутствуют либо некорректны"
        )

    return {
        "temp_c": float(temperature),
        "description": WEATHER_DESCRIPTIONS.get(
            weather_code, f"weather code {weather_code}"
        ),
        "weather_code": weather_code,
    }
