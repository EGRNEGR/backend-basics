"""Общая заготовка из условия ДЗ4: список URL и замер времени."""

import time
from collections.abc import Callable
from typing import Any

# 20 разных картинок (у каждой свой номер в адресе) - ответы достаточно
# «тяжёлые», чтобы разница между sync и async была хорошо видна
URLS = [f"https://picsum.photos/seed/{i}/800/600" for i in range(20)]

# Битые адреса для задания 2
BROKEN_URLS = [
    "https://no-such-site.invalid",  # домена не существует, упадёт сразу
    "https://httpbin.org/delay/10",  # отвечает 10 секунд, должен сработать таймаут
]


def timed(label: str, fn: Callable[..., Any], *args: Any) -> Any:
    """Запускает fn(*args), печатает, сколько секунд она работала, и возвращает результат."""
    start = time.perf_counter()
    result = fn(*args)
    print(f"{label}: {time.perf_counter() - start:.2f}s")
    return result
