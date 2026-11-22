import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import PlanResponse

pytestmark = pytest.mark.security


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as test_client:
        middleware = app.middleware_stack
        while middleware is not None:
            records = getattr(middleware, "ip_records", None)
            if records is not None:
                records.clear()
                break
            middleware = getattr(middleware, "app", None)
        yield test_client


@pytest.mark.parametrize(
    "payload",
    ["<script>alert(1)</script>", "' OR 1=1; --", "Delhi\u0000North", "दिल्ली"],
)
def test_plan_handles_untrusted_unicode_and_markup_as_plain_text(client, payload):
    body = {
        "location": payload,
        "aqi": 120,
        "household": "adults",
        "commute": "car",
        "cooking_fuel": "lpg",
        "budget": "moderate",
    }
    response = client.post("/api/plan", json=body)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert PlanResponse.model_validate(response.json())


def test_aqi_place_rejects_html_and_coordinate_nan(client):
    assert client.get("/api/aqi", params={"place": "<script>"}).status_code == 422
    assert client.get("/api/aqi/coords?lat=NaN&lon=0").status_code == 422


def test_oversized_declared_request_body_is_rejected(client):
    response = client.post(
        "/api/plan",
        content=b" " * (64 * 1024 + 1),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413


def test_frontend_renders_api_strings_without_html_parsing():
    from pathlib import Path

    script = (Path(__file__).parents[2] / "static" / "app.js").read_text(encoding="utf-8")
    assert "innerHTML" not in script
    assert "textContent = item.action" in script
    assert "textContent = plan.summary" in script


def test_security_headers_are_present(client):
    headers = client.get("/healthz").headers
    assert "default-src 'self'" in headers["content-security-policy"]
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert headers["permissions-policy"] == "geolocation=(self)"


def test_cross_origin_requests_receive_no_cors_permission(client):
    response = client.get("/healthz", headers={"Origin": "https://attacker.invalid"})
    assert "access-control-allow-origin" not in response.headers
