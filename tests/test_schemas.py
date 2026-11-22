"""Input validation tests for the public request schema."""

import pytest
from pydantic import ValidationError

from app.schemas import PlanRequest

pytestmark = pytest.mark.unit


@pytest.fixture
def valid_payload():
    return {
        "location": "Delhi",
        "aqi": 100,
        "household": "adults",
        "health_factors": [],
        "commute": "car",
        "cooking_fuel": "lpg",
        "budget": "moderate",
    }


@pytest.mark.parametrize("aqi", [-1, 501])
def test_plan_request_rejects_aqi_outside_allowed_range(valid_payload, aqi):
    with pytest.raises(ValidationError):
        PlanRequest(**(valid_payload | {"aqi": aqi}))


def test_plan_request_rejects_oversized_location(valid_payload):
    with pytest.raises(ValidationError):
        PlanRequest(**(valid_payload | {"location": "x" * 81}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("household", "unknown"),
        ("health_factors", ["unknown"]),
        ("commute", "unknown"),
        ("cooking_fuel", "unknown"),
        ("budget", "unknown"),
    ],
)
def test_plan_request_rejects_unknown_enum_values(valid_payload, field, value):
    with pytest.raises(ValidationError):
        PlanRequest(**(valid_payload | {field: value}))


def test_plan_request_rejects_extra_fields(valid_payload):
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PlanRequest(**(valid_payload | {"unexpected": "value"}))
