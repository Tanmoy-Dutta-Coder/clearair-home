"""FastAPI application entry point for clearair-home.

Mounts static assets, applies pure ASGI security and rate-limiting middleware,
and exposes health, AQI auto-detection (place and coordinates), and air quality adaptation plan endpoints.
"""

import logging
import re
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.aqi_provider import AqiUnavailable, detect_aqi, detect_aqi_by_coords
from app.config import settings
from app.llm import personalise_plan
from app.rules import build_plan
from app.schemas import CoordsQuery, PlanRequest, PlanResponse

APP_VERSION = "1.0.0"

# Structured one-line logging format to stdout
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
)
logger = logging.getLogger("clearair")

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

# Constants
MAX_BODY_SIZE_BYTES = 64 * 1024  # 64 KB limit
RATE_LIMIT_REQUESTS = 60  # 60 requests
RATE_LIMIT_WINDOW_SECS = 60.0  # per minute
RATE_LIMIT_MAX_TRACKED_IPS = 10_000
PLACE_REGEX = re.compile(r"^[a-zA-Z0-9\s,.-]{2,80}$")


class SecurityAndRateLimitMiddleware:
    """Pure ASGI middleware for strict security headers, body size checks, and per-IP rate limiting."""

    def __init__(
        self,
        app: ASGIApp,
        max_requests: int = RATE_LIMIT_REQUESTS,
        window_seconds: float = RATE_LIMIT_WINDOW_SECS,
        trusted_proxy_ips: frozenset[str] = frozenset(),
        max_tracked_ips: int = RATE_LIMIT_MAX_TRACKED_IPS,
    ):
        self.app = app
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.trusted_proxy_ips = trusted_proxy_ips
        self.max_tracked_ips = max_tracked_ips
        self.ip_records: dict[str, deque[float]] = defaultdict(deque)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))

        # 1. Body size check based on content-length header
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > MAX_BODY_SIZE_BYTES:
                    response = JSONResponse(
                        status_code=413,
                        content={"detail": "Payload too large. Maximum body size is 64KB."},
                    )
                    await response(scope, receive, send)
                    return
            except ValueError:
                response = JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length header."},
                )
                await response(scope, receive, send)
                return

        # 2. Per-IP sliding window rate limiting
        client = scope.get("client")
        direct_ip = client[0] if client else "127.0.0.1"
        x_forwarded_for = headers.get(b"x-forwarded-for")
        if x_forwarded_for and (direct_ip in self.trusted_proxy_ips or "*" in self.trusted_proxy_ips):
            client_ip = x_forwarded_for.decode("latin1").split(",")[0].strip()
        else:
            client_ip = direct_ip
        now = time.time()
        window_start = now - self.window_seconds
        if client_ip not in self.ip_records:
            if len(self.ip_records) >= self.max_tracked_ips:
                least_recent_ip = min(self.ip_records, key=lambda ip: self.ip_records[ip][-1])
                del self.ip_records[least_recent_ip]
            self.ip_records[client_ip] = deque()
        timestamps = self.ip_records[client_ip]

        while timestamps and timestamps[0] < window_start:
            timestamps.popleft()

        if len(timestamps) >= self.max_requests:
            response = JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please wait a minute before retrying."},
            )
            await response(scope, receive, send)
            return

        timestamps.append(now)

        # 3. Security headers on response start
        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                res_headers = list(message.get("headers", []))
                res_headers.extend(
                    [
                        (
                            b"content-security-policy",
                            b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none';",
                        ),
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"strict-origin-when-cross-origin"),
                        (b"permissions-policy", b"geolocation=(self)"),
                    ]
                )
                message["headers"] = res_headers
            await send(message)

        await self.app(scope, receive, send_with_security_headers)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifecycle manager logging startup status without sensitive data."""
    ai_enabled = bool(settings.gemini_api_key and settings.gemini_api_key.strip())
    logger.info("Application startup: version=%s ai_enabled=%s", APP_VERSION, ai_enabled)
    yield


# Initialize FastAPI app (CORS closed by default; same-origin only)
app = FastAPI(
    title="clearair-home",
    description="Adaptive winter smog and air quality guidance for households",
    version=APP_VERSION,
    lifespan=lifespan,
)

# Attach security & rate-limiting middleware (pure ASGI)
# By default in container/proxy environments (Render, Cloud Run), trust loopback and wildcard
app.add_middleware(
    SecurityAndRateLimitMiddleware,
    trusted_proxy_ips=frozenset({"127.0.0.1", "::1", "*"}),
)

# Mount static directory for JS and CSS assets
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# Validation Error Handler: Clear 422 messages without leaking internals
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = []
    for error in exc.errors():
        field = " -> ".join(str(loc) for loc in error.get("loc", []) if loc != "body")
        msg = error.get("msg", "Invalid value")
        errors.append(f"{field}: {msg}" if field else msg)

    return JSONResponse(
        status_code=422,
        content={
            "detail": "Invalid input context",
            "errors": errors,
        },
    )


# Unhandled Exception Handler: Prevents stack trace disclosure in responses
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Internal error occurred: %s", type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again later."},
    )


# Route Handlers
@app.get("/", response_class=FileResponse, response_model=None)
async def get_root() -> FileResponse | JSONResponse:
    """Serve the single-page application dashboard."""
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return JSONResponse(status_code=404, content={"detail": "Dashboard index.html not found."})
    return FileResponse(index_file)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Readiness and liveness probe for Cloud Run."""
    return {"status": "ok"}


@app.get("/api/aqi", response_model=None)
async def get_aqi_detection(place: str = Query(..., min_length=2, max_length=80)) -> dict[str, Any] | JSONResponse:
    """Auto-detect current AQI from Open-Meteo with fallback to 503 on unavailability."""
    clean_place = place.strip()
    if not PLACE_REGEX.match(clean_place):
        raise HTTPException(
            status_code=422,
            detail="Place name contains invalid characters. Use letters, numbers, spaces, and commas.",
        )

    try:
        data = detect_aqi(clean_place)
        return data
    except AqiUnavailable:
        return JSONResponse(
            status_code=503,
            content={"detail": "AQI auto-detection currently unavailable. Please enter AQI manually."},
        )


@app.get("/api/aqi/coords", response_model=None)
async def get_aqi_by_coords(
    query: CoordsQuery = Depends(),  # noqa: B008 - standard FastAPI dependency pattern
) -> dict[str, Any] | JSONResponse:
    """Auto-detect current AQI near approximate coordinates.

    Coordinates are rounded to 2 decimals (~1 km grid) and never logged.
    """
    try:
        data = detect_aqi_by_coords(query.lat, query.lon)
        return data
    except AqiUnavailable:
        return JSONResponse(
            status_code=503,
            content={"detail": "AQI auto-detection currently unavailable. Please enter AQI manually."},
        )


@app.post("/api/plan", response_model=PlanResponse)
async def create_plan(request: PlanRequest) -> PlanResponse:
    """Generate a context-aware air quality plan and optionally personalise with Gemini."""
    baseline = build_plan(request)
    plan = personalise_plan(request, baseline)
    return plan
