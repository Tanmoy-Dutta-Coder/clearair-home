"""Focused HTTP API tests; Gemini is always replaced with a local mock."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.api


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        middleware = app.middleware_stack
        while middleware is not None:
            records = getattr(middleware, "ip_records", None)
            if records is not None:
                records.clear()
                break
            middleware = getattr(middleware, "app", None)
        yield test_client


@pytest.fixture
def plan_payload():
    return {
        "location": "Delhi",
        "aqi": 250,
        "household": "adults",
        "health_factors": [],
        "commute": "car",
        "cooking_fuel": "lpg",
        "budget": "moderate",
    }


def test_healthz_returns_ok(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_plan_endpoint_returns_personalized_plan_with_mocked_gemini(client, plan_payload, monkeypatch):
    from app import main

    monkeypatch.setattr(
        main, "personalise_plan", lambda _request, baseline: baseline.model_copy(update={"used_ai": True})
    )

    response = client.post("/api/plan", json=plan_payload)

    assert response.status_code == 200
    assert response.json()["used_ai"] is True
    assert response.json()["aqi_band"] == "Poor"


def test_plan_endpoint_falls_back_when_mocked_gemini_raises(client, plan_payload, monkeypatch):
    from app import llm

    mocked_gemini = MagicMock()
    mocked_gemini.models.generate_content.side_effect = RuntimeError("simulated Gemini failure")
    monkeypatch.setattr(llm.settings, "gemini_api_key", "test-only-key")
    monkeypatch.setattr(llm, "_get_genai_client", lambda: mocked_gemini)

    response = client.post("/api/plan", json=plan_payload)

    assert response.status_code == 200
    assert response.json()["used_ai"] is False
    assert response.json()["aqi_band"] == "Poor"
    assert "simulated Gemini failure" not in response.text


def test_healthz_includes_required_security_headers(client):
    headers = client.get("/healthz").headers

    assert "default-src 'self'" in headers["content-security-policy"]
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert headers["permissions-policy"] == "geolocation=(self)"


def test_repeated_health_requests_are_rate_limited(client):
    statuses = [client.get("/healthz").status_code for _ in range(61)]

    assert statuses.count(429) >= 1
