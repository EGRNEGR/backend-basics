import logging
import random
import re
import time
from typing import Any

import requests
from processing.errors import (
    ApiError,
    ApiNotFoundError,
    ApiStatusError,
    InvalidApiResponseError,
)

logger = logging.getLogger(__name__)
TIMEOUT = (3, 7)
MAX_ATTEMPTS = 3
RETRYABLE_STATUS_CODES = {500, 502, 503, 504}


def _backoff(attempt: int) -> float:
    return min(2 ** (attempt - 1) + random.uniform(0, 0.25), 4.0)


def _retry_after(response: requests.Response, attempt: int) -> float:
    value = response.headers.get("Retry-After", "")
    if re.fullmatch(r"\d+(?:\.\d+)?", value.strip()):
        return float(value)
    return _backoff(attempt)


def _sleep_before_retry(url: str, attempt: int, delay: float) -> None:
    logger.warning(
        "Temporary HTTP failure, retry %s/%s in %.2f seconds for %s",
        attempt + 1,
        MAX_ATTEMPTS,
        delay,
        url,
    )
    time.sleep(delay)


def get_json(
    url: str,
    params: dict[str, str | int | float] | None = None,
) -> dict[str, Any]:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(url, params=params, timeout=TIMEOUT)
        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
        ) as error:
            if attempt == MAX_ATTEMPTS:
                raise ApiError("сервис не ответил после повторных попыток") from error
            _sleep_before_retry(url, attempt, _backoff(attempt))
            continue

        if response.status_code == 429:
            if attempt == MAX_ATTEMPTS:
                raise ApiError("сервис ограничил частоту запросов (HTTP 429)")
            _sleep_before_retry(url, attempt, _retry_after(response, attempt))
            continue

        if response.status_code in RETRYABLE_STATUS_CODES:
            if attempt == MAX_ATTEMPTS:
                raise ApiError(
                    f"сервис временно недоступен (HTTP {response.status_code})"
                )
            _sleep_before_retry(url, attempt, _backoff(attempt))
            continue

        if response.status_code == 404:
            raise ApiNotFoundError("запрошенные данные не найдены")
        if response.status_code >= 400:
            raise ApiStatusError(response.status_code)

        content_type = response.headers.get("Content-Type", "").split(";", maxsplit=1)[
            0
        ]
        if content_type != "application/json" and not content_type.endswith("+json"):
            raise InvalidApiResponseError("сервис вернул ответ не в формате JSON")

        try:
            data = response.json()
        except ValueError as error:
            raise InvalidApiResponseError(
                "не удалось разобрать JSON-ответ сервиса"
            ) from error

        if not isinstance(data, dict):
            raise InvalidApiResponseError("ожидался JSON-объект")
        return data

    raise ApiError("не удалось получить ответ от внешнего сервиса")
