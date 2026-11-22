import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app import aqi_provider
from app.main import SecurityAndRateLimitMiddleware, app
from app.rules import build_plan
from app.schemas import BudgetTier, CommuteMode, CookingFuel, HouseholdType, PlanRequest

pytestmark = pytest.mark.performance
REQUEST = PlanRequest(
    location="Delhi",
    aqi=320,
    household=HouseholdType.ADULTS,
    commute=CommuteMode.CAR,
    cooking_fuel=CookingFuel.LPG,
    budget=BudgetTier.MODERATE,
)


def test_build_plan_microbenchmark(benchmark):
    result = benchmark(build_plan, REQUEST)
    assert len(result.routine) >= 3
    assert benchmark.stats.stats.mean < 0.05


def test_pm_to_indian_aqi_microbenchmark(benchmark):
    result = benchmark(aqi_provider.pm_to_indian_aqi, 115.0, 210.0)
    assert 0 <= result <= 500
    assert benchmark.stats.stats.mean < 0.001


def test_fifty_concurrent_health_requests_p95_under_two_seconds():
    client = TestClient(app)
    middleware = app.middleware_stack
    while middleware is not None:
        records = getattr(middleware, "ip_records", None)
        if records is not None:
            records.clear()
            break
        middleware = getattr(middleware, "app", None)
    timings = []

    def request_once(_index):
        started = time.perf_counter()
        response = client.get("/healthz")
        return response.status_code, time.perf_counter() - started

    with ThreadPoolExecutor(max_workers=50) as pool:
        results = list(pool.map(request_once, range(50)))
    timings = sorted(duration for status, duration in results if status == 200)
    assert len(timings) == 50
    assert timings[int(0.95 * (len(timings) - 1))] < 2.0


def test_aqi_cache_does_not_exceed_configured_capacity(monkeypatch):
    aqi_provider._CACHE.clear()
    monkeypatch.setattr(aqi_provider, "CACHE_MAX_ENTRIES", 32)
    for index in range(100):
        aqi_provider._set_in_cache(str(index), {"aqi": index})
    assert len(aqi_provider._CACHE) <= 32
    aqi_provider._CACHE.clear()


def test_rate_limiter_tracking_stays_bounded_for_many_unique_clients():
    async def exercise():
        async def ok_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        limiter = SecurityAndRateLimitMiddleware(ok_app, max_requests=60)

        async def call(index):
            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(_message):
                return None

            scope = {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [],
                "client": (f"192.0.{index // 250}.{index % 250}", 1234),
            }
            await limiter(scope, receive, send)

        for index in range(10_001):
            await call(index)
        assert len(limiter.ip_records) <= 10_000

    asyncio.run(exercise())
