import logging
import math
import time

from processing.errors import (
    ApiNotFoundError,
    ApiStatusError,
    CurrencyNotFoundError,
    InvalidApiResponseError,
)

from clients.http import get_json

logger = logging.getLogger(__name__)
RATES_URL = "https://api.frankfurter.dev/v2/rate"
CACHE_TTL_SECONDS = 300
_rate_cache: dict[str, tuple[float, float]] = {}


def get_rate(currency: str) -> float:
    normalized = currency.upper()
    if normalized == "RUB":
        return 1.0

    now = time.monotonic()
    cached = _rate_cache.get(normalized)
    if cached is not None and cached[0] > now:
        logger.info("Using cached exchange rate for %s", normalized)
        return cached[1]

    try:
        payload = get_json(f"{RATES_URL}/{normalized}/RUB")
    except ApiNotFoundError as error:
        raise CurrencyNotFoundError(f"код валюты «{normalized}» не найден") from error
    except ApiStatusError as error:
        if error.status_code in {400, 422}:
            raise CurrencyNotFoundError(
                f"код валюты «{normalized}» не найден"
            ) from error
        raise

    base = payload.get("base")
    quote = payload.get("quote")
    rate = payload.get("rate")
    if base != normalized or quote != "RUB":
        raise InvalidApiResponseError(
            "пара валют в ответе курса не совпадает с запросом"
        )
    if (
        not isinstance(rate, (int, float))
        or isinstance(rate, bool)
        or not math.isfinite(float(rate))
        or rate <= 0
    ):
        raise InvalidApiResponseError("значение курса отсутствует или некорректно")

    result = float(rate)
    _rate_cache[normalized] = (now + CACHE_TTL_SECONDS, result)
    return result
