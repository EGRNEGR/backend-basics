"""Задание 3 (*). Вынос CPU-bound-вычислений

Замеры (20 картинок picsum.photos, heavy = sha256(body * 1000)):
    Windows 11, Python 3.14.7, домашний интернет, 25.10.2026; два прогона подряд. 16 логических ядер, пул из 8 процессов.
    blocking    : 2.28s, 1.49s - тиков ticker: 0 и 0 (loop стоял)
    process pool: 0.37s, 0.23s - тиков ticker: 3 и 2 (ожидалось ~4 и ~2)

Что видно.
    ticker печатает точку каждые 0.1 s - это «пульс» event loop. Программа
    считает, сколько тиков успело пройти за время хеширования, и печатает
    это число рядом с замером.

    - «В лоб» (blocking): heavy вызывается прямо в корутине. sha256 от
      десятков мегабайт - чистая работа CPU без единого await, поэтому loop
      не может переключиться на ticker, пока не посчитаны все хеши. Точки
      замирают: за 1.5-2.3 s вычислений не проходит ни одного тика.
    - ProcessPoolExecutor: каждый heavy отправляется в отдельный процесс
      через loop.run_in_executor, а корутина только ждёт future. Loop
      свободен, ticker продолжает печатать точки всё время вычислений, а
      хеши считаются параллельно на нескольких ядрах. ThreadPoolExecutor
      здесь хуже: вычисления в Python-коде держат GIL, и потоки не дают
      настоящего параллелизма для CPU-bound-задач.

Запуск (из каталога lab3-4):
    python -m async_loader.task3_cpu_bound
"""

import asyncio
import hashlib
import os
import time
from concurrent.futures import ProcessPoolExecutor

import httpx

from async_loader.common import URLS

TICK = 0.1
WORKERS = min(os.cpu_count() or 1, 8)


def heavy(body: bytes) -> str:
    # body * 1000 раздувает данные, чтобы хеш считался заметно долго
    return hashlib.sha256(body * 1000).hexdigest()


async def ticker(counter: list[int]) -> None:
    # «пульс» event loop: если точки перестали печататься - loop заблокирован
    while True:
        print(".", end="", flush=True)
        counter[0] += 1
        await asyncio.sleep(TICK)


async def download_all(urls: list[str]) -> list[bytes]:
    async with (
        httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client,
        asyncio.TaskGroup() as group,
    ):
        tasks = [group.create_task(client.get(url)) for url in urls]
    return [task.result().raise_for_status().content for task in tasks]


async def hash_blocking(bodies: list[bytes]) -> list[str]:
    # ошибка намеренная: CPU-bound прямо в корутине блокирует event loop
    return [heavy(body) for body in bodies]


async def hash_in_processes(
    bodies: list[bytes], pool: ProcessPoolExecutor
) -> list[str]:
    loop = asyncio.get_running_loop()
    return await asyncio.gather(
        *(loop.run_in_executor(pool, heavy, body) for body in bodies)
    )


async def measure(label: str, job) -> tuple[list[str], float, int]:
    """Выполняет job под работающим ticker; возвращает (хеши, секунды, число тиков)."""
    counter = [0]
    pulse = asyncio.create_task(ticker(counter))
    await asyncio.sleep(0)  # дать ticker стартовать и напечатать первую точку
    start = time.perf_counter()
    hashes = await job
    elapsed = time.perf_counter() - start
    pulse.cancel()
    ticks = counter[0] - 1  # первая точка напечатана до начала замера
    print(
        f"\n{label}: {elapsed:.2f}s, тиков ticker: {ticks} (ожидалось ~{elapsed / TICK:.0f})"
    )
    return hashes, elapsed, ticks


async def cpu_main(urls: list[str] = URLS) -> None:
    bodies = await download_all(urls)
    total_mb = sum(len(body) for body in bodies) * 1000 / 1_000_000
    print(f"скачано {len(bodies)} ответов, хешируем ~{total_mb:.0f} MB")

    blocking, _, _ = await measure("blocking", hash_blocking(bodies))
    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        # прогрев: процессы стартуют заранее, чтобы замер был только про вычисления
        await hash_in_processes([b""] * WORKERS, pool)
        offloaded, _, _ = await measure("process pool", hash_in_processes(bodies, pool))
    assert blocking == offloaded, "оба способа должны давать одинаковые хеши"


if __name__ == "__main__":
    asyncio.run(cpu_main())
