"""Tests for FastAPI endpoints, security headers, rate limiting, and AQI detection."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.aqi_provider import AqiUnavailable
from app.main import app
from app.schemas import ActionItem, PlanResponse

pytestmark = pytest.mark.api
client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def clear_rate_limit_state():
    """Keep the middleware's in-memory limiter isolated between API tests."""
    middleware = app.middleware_stack
    while middleware is not None:
        records = getattr(middleware, "ip_records", None)
        if records is not None:
            records.clear()
            break
        middleware = getattr(middleware, "app", None)


def test_healthz_with_fastapi_testclient():
    """Verify GET /healthz using FastAPI TestClient returns 200 OK and expected body."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_security_headers_present():
    """Verify all mandatory security headers are attached on every response."""
    response = client.get("/healthz")
    headers = response.headers

    # Content-Security-Policy restricting to self
    assert "default-src 'self'" in headers.get("Content-Security-Policy", "")
    assert "frame-ancestors 'none'" in headers.get("Content-Security-Policy", "")

    # Standard security headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert headers.get("Permissions-Policy") == "geolocation=(self)"


def test_valid_plan_call_with_llm_mocked():
    """Verify POST /api/plan returns 200 and used_ai=True when Gemini succeeds."""
    mock_item = ActionItem(
        action="Wear an N95 respirator outdoors",
        why="Personalized: Protect against elevated winter particulates in Delhi.",
        impact="Roughly 95% particulate filtration (certified standard basis).",
    )
    mock_personalized_plan = PlanResponse(
        aqi_band="Very Poor",
        summary="AI-personalized winter smog action plan for your household.",
        routine=[mock_item, mock_item, mock_item],
        indoor=[mock_item, mock_item, mock_item],
        swaps=[mock_item, mock_item, mock_item],
        used_ai=True,
    )

    payload = {
        "location": "Delhi NCR",
        "aqi": 340,
        "household": "children_and_elderly",
        "health_factors": ["asthma"],
        "commute": "car",
        "cooking_fuel": "lpg",
        "budget": "moderate",
    }

    with patch("app.main.personalise_plan", return_value=mock_personalized_plan) as mock_llm:
        response = client.post("/api/plan", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["aqi_band"] == "Very Poor"
        assert data["used_ai"] is True
        assert "AI-personalized" in data["summary"]
        assert len(data["routine"]) == 3
        assert len(data["indoor"]) == 3
        assert len(data["swaps"]) == 3
        mock_llm.assert_called_once()


def test_plan_fallback_path_when_llm_raises_error():
    """Verify POST /api/plan falls back gracefully to baseline plan (used_ai=False) when LLM fails."""
    payload = {
        "location": "Delhi",
        "aqi": 320,
        "household": "adults",
        "health_factors": [],
        "commute": "two_wheeler",
        "cooking_fuel": "lpg",
        "budget": "moderate",
    }

    # Simulate Gemini client throwing an API / network / timeout error inside app.llm
    with patch("app.llm._get_genai_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("Gemini API connection error")
        mock_get_client.return_value = mock_client

        response = client.post("/api/plan", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["used_ai"] is False
        assert data["aqi_band"] == "Very Poor"
        assert len(data["routine"]) >= 3
        assert len(data["indoor"]) >= 3
        assert len(data["swaps"]) >= 3


def test_plan_fallback_when_gemini_key_missing():
    """Verify fallback to baseline plan when no Gemini API key is configured."""
    payload = {
        "location": "Bengaluru",
        "aqi": 85,
        "household": "adults",
        "health_factors": [],
        "commute": "car",
        "cooking_fuel": "induction",
        "budget": "moderate",
    }
    with patch("app.llm.settings.gemini_api_key", ""):
        response = client.post("/api/plan", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["used_ai"] is False
        assert data["aqi_band"] == "Satisfactory"


def test_rate_limit_returning_429():
    """Verify that rapid requests from a single IP hit the rate limit and return HTTP 429."""
    client_ip_headers = {"X-Forwarded-For": "203.0.113.195"}
    responses = []

    # Send requests to exceed the per-IP threshold (60 requests per minute)
    for _ in range(65):
        res = client.get("/healthz", headers=client_ip_headers)
        responses.append(res.status_code)

    assert 429 in responses
    # Confirm 429 error response body contains clear message
    res_429 = client.get("/healthz", headers=client_ip_headers)
    assert res_429.status_code == 429
    assert "Too Many Requests" in res_429.text or "rate limit" in res_429.text.lower()


def test_root_index_served():
    """Verify GET / serves static/index.html with correct metadata."""
    response = client.get("/")
    assert response.status_code == 200
    assert "ClearAir Home" in response.text
    assert 'lang="en"' in response.text


def test_static_assets_security():
    """Verify static assets are served and JavaScript avoids innerHTML."""
    res_css = client.get("/static/styles.css")
    assert res_css.status_code == 200
    assert "@media print" in res_css.text

    res_js = client.get("/static/app.js")
    assert res_js.status_code == 200
    assert "textContent" in res_js.text
    assert "innerHTML" not in res_js.text


def test_aqi_endpoint_success():
    """Verify GET /api/aqi returns 200 with detected AQI."""
    mock_data = {
        "aqi": 340,
        "band": "Very Poor",
        "source": "Open-Meteo",
        "observed_at": "2026-11-23T00:00",
        "area": "Delhi",
    }
    with patch("app.main.detect_aqi", return_value=mock_data):
        response = client.get("/api/aqi?place=Delhi")
        assert response.status_code == 200
        data = response.json()
        assert data["aqi"] == 340
        assert data["band"] == "Very Poor"


def test_aqi_endpoint_503_fallback():
    """Verify GET /api/aqi returns 503 with friendly message when provider fails."""
    with patch("app.main.detect_aqi", side_effect=AqiUnavailable("Lookup failed")):
        response = client.get("/api/aqi?place=UnknownPlace")
        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()


def test_aqi_endpoint_invalid_place():
    """Verify GET /api/aqi rejects invalid or oversized place query strings."""
    # Too short (< 2 chars)
    res_short = client.get("/api/aqi?place=a")
    assert res_short.status_code == 422

    # Invalid characters (potential injection attempt)
    res_invalid = client.get("/api/aqi?place=Delhi<script>")
    assert res_invalid.status_code == 422


def test_aqi_by_coords_endpoint_success():
    """Verify GET /api/aqi/coords returns 200 with approximate AQI."""
    mock_data = {
        "aqi": 285,
        "band": "Poor",
        "source": "Open-Meteo",
        "observed_at": "2026-11-23T00:00",
        "area": "Your current location (approx.)",
        "approximate_location": True,
    }
    with patch("app.main.detect_aqi_by_coords", return_value=mock_data):
        response = client.get("/api/aqi/coords?lat=28.61&lon=77.21")
        assert response.status_code == 200
        data = response.json()
        assert data["aqi"] == 285
        assert data["approximate_location"] is True


def test_aqi_by_coords_endpoint_503_fallback():
    """Verify GET /api/aqi/coords returns 503 on provider failure and does not leak coords."""
    with patch("app.main.detect_aqi_by_coords", side_effect=AqiUnavailable("Failed")):
        response = client.get("/api/aqi/coords?lat=28.61&lon=77.21")
        assert response.status_code == 503
        body_text = response.text
        assert "unavailable" in body_text.lower()
        assert "28.61" not in body_text
        assert "77.21" not in body_text


def test_aqi_by_coords_validation_error():
    """Verify GET /api/aqi/coords returns 422 on invalid coordinate values."""
    res_lat = client.get("/api/aqi/coords?lat=95.0&lon=77.0")
    assert res_lat.status_code == 422

    res_lon = client.get("/api/aqi/coords?lat=28.0&lon=190.0")
    assert res_lon.status_code == 422

    res_str = client.get("/api/aqi/coords?lat=invalid&lon=77.0")
    assert res_str.status_code == 422


def test_root_and_health_content_types_are_html_and_json():
    assert "text/html" in client.get("/").headers["content-type"]
    assert "application/json" in client.get("/healthz").headers["content-type"]


@pytest.mark.parametrize("method,path", [("get", "/missing"), ("post", "/healthz"), ("get", "/api/plan")])
def test_unknown_route_and_method_return_standard_errors(method, path):
    response = getattr(client, method)(path)
    assert response.status_code in (404, 405, 422)
    assert "Traceback" not in response.text


def test_plan_response_validates_against_response_model():
    from app.rules import build_plan
    from app.schemas import PlanRequest

    request = PlanRequest(
        location="Delhi",
        aqi=100,
        household="adults",
        commute="car",
        cooking_fuel="lpg",
        budget="moderate",
    )
    with patch("app.main.personalise_plan", side_effect=lambda _request, plan: plan):
        response = client.post("/api/plan", json=request.model_dump(mode="json"))
    assert response.status_code == 200
    parsed = PlanResponse.model_validate(response.json())
    assert parsed == build_plan(request)


def test_openapi_declares_core_paths_and_plan_response_schema():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert {"/", "/healthz", "/api/plan", "/api/aqi", "/api/aqi/coords"} <= set(spec["paths"])
    plan_schema = spec["paths"]["/api/plan"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert plan_schema["$ref"].endswith("/PlanResponse")


def test_cors_is_not_enabled():
    response = client.get("/healthz", headers={"Origin": "https://example.invalid"})
    assert "access-control-allow-origin" not in response.headers


def test_error_response_does_not_expose_exception_details():
    payload = {
        "location": "Delhi",
        "aqi": 100,
        "household": "adults",
        "commute": "car",
        "cooking_fuel": "lpg",
        "budget": "moderate",
    }
    with patch("app.main.build_plan", side_effect=RuntimeError("private-token-xyz")):
        response = client.post("/api/plan", json=payload)
    assert response.status_code == 500
    assert "private-token-xyz" not in response.text
    assert "Traceback" not in response.text
