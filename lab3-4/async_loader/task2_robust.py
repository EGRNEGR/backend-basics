"""Задание 2. Реальный I/O и обработка ошибок

Замеры (20 картинок picsum.photos + 2 битых адреса):
    Windows 11, Python 3.14.7, домашний интернет, 25.10.2026; два прогона подряд.
    robust: 22.45s, 22.52s - успешно 20, ошибок 2:
      https://no-such-site.invalid: ConnectError после 3 попыток
      https://httpbin.org/delay/10: ReadTimeout после 3 попыток

Что сделано.
    - Таймаут на каждый запрос: httpx.Timeout(5 s) на подключение и на
      чтение. https://httpbin.org/delay/10 молчит 10 секунд, поэтому каждая
      попытка обрывается по ReadTimeout через 5 секунд.
    - Ретраи с экспоненциальным backoff: 3 попытки, паузы между ними
      1 s -> 2 s (следующая была бы 4 s). Повторяются только временные сбои:
      сетевые ошибки и таймауты (httpx.TransportError), ответы 429 и 5xx.
      Ошибка 4xx - проблема самого запроса, её повтор бессмыслен.
    - Устойчивость: каждый URL обрабатывается в своей задаче, исключение
      ловится внутри неё и превращается в запись об ошибке. Поэтому один
      битый адрес не отменяет остальные задачи TaskGroup, а robust_main
      возвращает кортеж (результаты, ошибки).

Почему общее время около 22 s: его задаёт самый долгий URL - delay/10:
3 попытки по 5 s таймаута чтения + паузы 1 s и 2 s = 18 s, плюс новое
TLS-подключение к httpbin на каждой попытке (после таймаута соединение
закрывается). Остальные 21 адрес завершаются параллельно за это время. Несуществующий домен падает за доли
секунды на каждой попытке, так что для него время - это в основном паузы
backoff (около 3 s).

Запуск (из каталога lab3-4):
    python -m async_loader.task2_robust
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

from async_loader.common import BROKEN_URLS, URLS, timed

TIMEOUT = httpx.Timeout(5.0)
MAX_ATTEMPTS = 3
BASE_DELAY = 1.0
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class FetchResult:
    url: str
    status_code: int
    size: int


@dataclass(frozen=True)
class FetchError:
    url: str
    error: str
    attempts: int


class FetchFailedError(Exception):
    def __init__(self, url: str, attempts: int, cause: Exception) -> None:
        super().__init__(f"{url}: {type(cause).__name__} после {attempts} попыток")
        self.url = url
        self.attempts = attempts
        self.cause = cause


def backoff_delay(attempt: int, base: float = BASE_DELAY) -> float:
    """Пауза после неудачной попытки attempt (с 1): 1 s, 2 s, 4 s, ..."""
    return base * 2 ** (attempt - 1)


def _is_retryable(error: Exception) -> bool:
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in RETRYABLE_STATUS_CODES
    return isinstance(error, httpx.TransportError)


async def robust_fetch(
    client: httpx.AsyncClient,
    url: str,
    *,
    attempts: int = MAX_ATTEMPTS,
    base_delay: float = BASE_DELAY,
    sleep: Sleep = asyncio.sleep,
) -> FetchResult:
    """Скачивает url с таймаутом и ретраями; после последней неудачи бросает FetchFailedError."""
    for attempt in range(1, attempts + 1):
        try:
            response = await client.get(url, timeout=TIMEOUT)
            response.raise_for_status()
            return FetchResult(url, response.status_code, len(response.content))
        except (httpx.TransportError, httpx.HTTPStatusError) as error:
            if attempt == attempts or not _is_retryable(error):
                raise FetchFailedError(url, attempt, error) from error
            await sleep(backoff_delay(attempt, base_delay))
    raise AssertionError("unreachable: attempts must be >= 1")


async def _fetch_or_error(
    client: httpx.AsyncClient, url: str, sleep: Sleep
) -> FetchResult | FetchError:
    try:
        return await robust_fetch(client, url, sleep=sleep)
    except FetchFailedError as error:
        return FetchError(url, str(error), error.attempts)


async def robust_main(
    urls: list[str] = URLS + BROKEN_URLS,
    *,
    client: httpx.AsyncClient | None = None,
    sleep: Sleep = asyncio.sleep,
) -> tuple[list[FetchResult], list[FetchError]]:
    """Скачивает все urls; битые не роняют остальные. Возвращает (результаты, ошибки)."""
    async with (
        client or httpx.AsyncClient(follow_redirects=True) as http,
        asyncio.TaskGroup() as group,
    ):
        tasks = [group.create_task(_fetch_or_error(http, url, sleep)) for url in urls]
    outcomes = [task.result() for task in tasks]
    results = [item for item in outcomes if isinstance(item, FetchResult)]
    errors = [item for item in outcomes if isinstance(item, FetchError)]
    return results, errors


if __name__ == "__main__":
    results, errors = timed("robust", lambda: asyncio.run(robust_main()))
    print(f"успешно: {len(results)}, ошибок: {len(errors)}")
    for error in errors:
        print(f"  {error.error}")
