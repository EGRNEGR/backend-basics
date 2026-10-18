from clients.rates import get_rate
from clients.weather import get_weather

from processing.preprocessing import apply_rate_rules, apply_weather_rules


def build_city_summary(city: str, currency: str = "USD") -> dict[str, object]:
    weather = apply_weather_rules(get_weather(city))
    rate_to_rub = get_rate(currency)
    return {
        "city": city.strip(),
        "weather": weather,
        "rates": apply_rate_rules(currency.upper(), rate_to_rub),
    }
