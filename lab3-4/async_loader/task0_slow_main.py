"""Задание 0. Разминка-ловушка «Почему не быстрее?»

Замеры (20 картинок picsum.photos, 800x600; Windows 11, Python 3.14.7, домашний интернет, 25.10.2026; два прогона подряд):
    slow : 8.73s, 7.95s
    fixed: 2.83s, 2.79s  (примерно в 3 раза быстрее)

Почему async не дал ускорения.
    В slow_main запросы ждутся по очереди: `await fetch(...)` внутри `for`
    приостанавливает корутину до конца текущего запроса, и следующий запрос
    даже не начинается. Event loop в это время свободен, но ему нечего
    выполнять - в нём всего одна задача. Получается тот же последовательный
    цикл, что и с requests, только с накладными расходами на event loop:
    время равно сумме времён всех запросов. (slow_main всё же быстрее
    sync_main из задания 1, потому что один AsyncClient переиспользует
    keep-alive соединение, а requests.get каждый раз открывает новое
    TLS-соединение.)

Как починено.
    fixed_main сначала создаёт корутины для всех URL и передаёт их в
    asyncio.gather: все запросы стартуют сразу, и пока один ждёт сеть,
    loop переключается на остальные. Общее время - примерно время самого
    долгого запроса, а не сумма. `follow_redirects=True` обязателен:
    picsum отвечает 302, и без флага httpx вернул бы короткий редирект
    вместо картинки.

Запуск (из каталога lab3-4):
    python -m async_loader.task0_slow_main
"""

import asyncio

import httpx

from async_loader.common import URLS, timed


async def fetch(client: httpx.AsyncClient, url: str) -> int:
    resp = await client.get(url)
    return resp.status_code


async def slow_main(urls: list[str] = URLS) -> list[int]:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        statuses = []
        for url in urls:
            statuses.append(await fetch(client, url))  # ждём каждый запрос по очереди
        return statuses


async def fixed_main(urls: list[str] = URLS) -> list[int]:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        # все запросы запускаются конкурентно, gather ждёт их вместе
        return await asyncio.gather(*(fetch(client, url) for url in urls))


if __name__ == "__main__":
    # lambda нужна, чтобы asyncio.run выполнился внутри timed, а не до замера
    timed("slow ", lambda: asyncio.run(slow_main()))
    timed("fixed", lambda: asyncio.run(fixed_main()))
