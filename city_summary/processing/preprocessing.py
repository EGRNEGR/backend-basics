from typing import Any


def apply_weather_rules(weather: dict[str, Any]) -> dict[str, Any]:
    processed = dict(weather)
    processed["warm_clothes"] = processed["temp_c"] < 0
    description = processed.get("description")
    if not isinstance(description, str) or not description.strip():
        processed["description"] = "unknown weather"
    return processed


def apply_rate_rules(currency: str, rate_to_rub: float) -> dict[str, Any]:
    return {
        "currency": currency,
        "rate_to_rub": rate_to_rub,
        "expensive": rate_to_rub > 100,
    }
