import asyncio

import pytest

from app.main import SecurityAndRateLimitMiddleware

pytestmark = pytest.mark.security


async def _request(middleware, forwarded_for):
    sent = []

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"x-forwarded-for", forwarded_for.encode())],
        "client": ("192.0.2.10", 1234),
    }

    async def send(message):
        sent.append(message)

    await middleware(scope, receive, send)
    return next(message["status"] for message in sent if message["type"] == "http.response.start")


def test_rate_limit_cannot_be_bypassed_by_changing_forwarded_ip():
    async def run():
        async def unused_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = SecurityAndRateLimitMiddleware(unused_app, max_requests=1)
        assert await _request(middleware, "198.51.100.1") == 200
        assert await _request(middleware, "203.0.113.2") == 429

    pytest.importorskip("anyio")
    asyncio.run(run())
