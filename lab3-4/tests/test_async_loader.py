import asyncio
import hashlib
import time
from concurrent.futures import ProcessPoolExecutor
from functools import partial

import httpx
import pytest

from async_loader import (
    task0_slow_main,
    task1_sync_vs_async,
    task2_robust,
    task3_cpu_bound,
)

URLS = [f"https://example.test/image/{i}" for i in range(10)]
LATENCY = 0.2


async def slow_handler(request: httpx.Request) -> httpx.Response:
    await asyncio.sleep(LATENCY)
    return httpx.Response(200, content=b"image")


@pytest.fixture
def mock_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every AsyncClient created by the code under test talks to slow_handler."""
    client_cls = httpx.AsyncClient
    transport = httpx.MockTransport(slow_handler)
    monkeypatch.setattr(httpx, "AsyncClient", partial(client_cls, transport=transport))


def run_timed(coro) -> tuple[object, float]:
    start = time.perf_counter()
    result = asyncio.run(coro)
    return result, time.perf_counter() - start


def test_slow_main_waits_requests_one_by_one(mock_network: None) -> None:
    statuses, elapsed = run_timed(task0_slow_main.slow_main(URLS))
    assert statuses == [200] * len(URLS)
    assert elapsed >= LATENCY * len(URLS) * 0.9


def test_fixed_main_runs_requests_concurrently(mock_network: None) -> None:
    statuses, elapsed = run_timed(task0_slow_main.fixed_main(URLS))
    assert statuses == [200] * len(URLS)
    assert elapsed < LATENCY * 3


def test_fast_main_runs_requests_concurrently(mock_network: None) -> None:
    statuses, elapsed = run_timed(task1_sync_vs_async.fast_main(URLS))
    assert statuses == [200] * len(URLS)
    assert elapsed < LATENCY * 3


def test_sync_main_uses_requests_sequentially(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    class FakeResponse:
        status_code = 200

    def fake_get(url: str, timeout: float) -> FakeResponse:
        calls.append(url)
        return FakeResponse()

    monkeypatch.setattr(task1_sync_vs_async.requests, "get", fake_get)
    assert task1_sync_vs_async.sync_main(URLS) == [200] * len(URLS)
    assert calls == URLS


def test_backoff_grows_exponentially() -> None:
    delays = [task2_robust.backoff_delay(attempt) for attempt in (1, 2, 3)]
    assert delays == [1.0, 2.0, 4.0]


class FakeSleep:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def scripted_client(outcomes: list[httpx.Response | Exception]) -> httpx.AsyncClient:
    script = iter(outcomes)

    def handler(request: httpx.Request) -> httpx.Response:
        outcome = next(script)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def fetch_with(
    client: httpx.AsyncClient, sleep: FakeSleep
) -> task2_robust.FetchResult:
    async with client:
        return await task2_robust.robust_fetch(
            client, "https://example.test/x", sleep=sleep
        )


def test_robust_fetch_retries_transient_errors_then_succeeds() -> None:
    sleep = FakeSleep()
    client = scripted_client(
        [
            httpx.ConnectError("boom"),
            httpx.Response(503),
            httpx.Response(200, content=b"ok"),
        ]
    )
    result = asyncio.run(fetch_with(client, sleep))
    assert result == task2_robust.FetchResult("https://example.test/x", 200, 2)
    assert sleep.delays == [1.0, 2.0]


def test_robust_fetch_gives_up_after_three_timeouts() -> None:
    sleep = FakeSleep()
    client = scripted_client([httpx.ReadTimeout("slow")] * 3)
    with pytest.raises(task2_robust.FetchFailedError) as error:
        asyncio.run(fetch_with(client, sleep))
    assert error.value.attempts == 3
    assert isinstance(error.value.cause, httpx.ReadTimeout)
    assert sleep.delays == [1.0, 2.0]


def test_robust_fetch_does_not_retry_client_errors() -> None:
    sleep = FakeSleep()
    client = scripted_client([httpx.Response(404)])
    with pytest.raises(task2_robust.FetchFailedError) as error:
        asyncio.run(fetch_with(client, sleep))
    assert error.value.attempts == 1
    assert sleep.delays == []


def test_robust_fetch_sets_timeout_on_every_request() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions["timeout"])
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    asyncio.run(fetch_with(client, FakeSleep()))
    assert seen == [{"connect": 5.0, "read": 5.0, "write": 5.0, "pool": 5.0}]


def test_robust_main_isolates_broken_urls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "no-such-site.invalid":
            raise httpx.ConnectError("name resolution failed")
        if request.url.path.startswith("/delay"):
            raise httpx.ReadTimeout("timed out")
        return httpx.Response(200, content=b"image")

    urls = [
        "https://ok.test/1",
        "https://no-such-site.invalid",
        "https://ok.test/2",
        "https://httpbin.test/delay/10",
    ]
    sleep = FakeSleep()
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    results, errors = asyncio.run(
        task2_robust.robust_main(urls, client=client, sleep=sleep)
    )

    assert [r.url for r in results] == ["https://ok.test/1", "https://ok.test/2"]
    assert [e.url for e in errors] == [
        "https://no-such-site.invalid",
        "https://httpbin.test/delay/10",
    ]
    assert all(e.attempts == 3 for e in errors)
    assert "ConnectError" in errors[0].error and "ReadTimeout" in errors[1].error
    assert sorted(sleep.delays) == [1.0, 1.0, 2.0, 2.0]


def test_heavy_is_sha256_of_inflated_body() -> None:
    assert task3_cpu_bound.heavy(b"ab") == hashlib.sha256(b"ab" * 1000).hexdigest()


def test_blocking_hash_freezes_ticker_and_process_pool_does_not() -> None:
    bodies = [bytes([i]) * 300_000 for i in range(8)]

    async def scenario() -> tuple[int, int, bool]:
        blocking, _, blocked_ticks = await task3_cpu_bound.measure(
            "blocking", task3_cpu_bound.hash_blocking(bodies)
        )
        with ProcessPoolExecutor(max_workers=2) as pool:
            offloaded, _, pool_ticks = await task3_cpu_bound.measure(
                "process pool", task3_cpu_bound.hash_in_processes(bodies, pool)
            )
        return blocked_ticks, pool_ticks, blocking == offloaded

    blocked_ticks, pool_ticks, same_hashes = asyncio.run(scenario())
    assert blocked_ticks == 0
    assert pool_ticks >= 1
    assert same_hashes
