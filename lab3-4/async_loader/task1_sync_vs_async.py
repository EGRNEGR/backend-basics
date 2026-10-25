"""Задание 1. Синхронно vs асинхронно

Замеры (20 картинок picsum.photos, 800x600; Windows 11, Python 3.14.7, домашний интернет, 25.10.2026; два прогона подряд):
    sync : 29.05s, 47.72s
    async: 3.08s, 2.98s  (в 10-16 раз быстрее)

Разница в одну строку: requests ждёт каждый ответ, прежде чем отправить
следующий запрос, и времена складываются, а httpx.AsyncClient + TaskGroup
держит все 20 запросов в сети одновременно, поэтому общее время близко
к времени самого медленного ответа.

Запуск (из каталога lab3-4):
    python -m async_loader.task1_sync_vs_async
"""

import asyncio

import httpx
import requests

from async_loader.common import URLS, timed
from async_loader.task0_slow_main import fetch

TIMEOUT = 30.0


def sync_main(urls: list[str] = URLS) -> list[int]:
    statuses = []
    for url in urls:
        # по очереди, время складывается
        statuses.append(requests.get(url, timeout=TIMEOUT).status_code)
    return statuses


async def fast_main(urls: list[str] = URLS) -> list[int]:
    async with (
        httpx.AsyncClient(follow_redirects=True, timeout=TIMEOUT) as client,
        asyncio.TaskGroup() as group,
    ):
        tasks = [group.create_task(fetch(client, url)) for url in urls]
    return [task.result() for task in tasks]


if __name__ == "__main__":
    timed("sync ", sync_main)
    timed("async", lambda: asyncio.run(fast_main()))
