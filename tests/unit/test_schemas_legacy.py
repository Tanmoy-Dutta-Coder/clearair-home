"""Unit tests for Pydantic request and response schemas."""

import pytest
from pydantic import ValidationError

from app.schemas import (
    ActionItem,
    BudgetTier,
    CommuteMode,
    CookingFuel,
    CoordsQuery,
    HealthFactor,
    HouseholdType,
    PlanRequest,
    PlanResponse,
)

pytestmark = pytest.mark.unit


def test_plan_request_valid():
    """Verify valid request passes parsing, normalizes enums, and strips whitespace."""
    req = PlanRequest(
        location="  Delhi NCR  ",
        aqi=280,
        household=HouseholdType.CHILDREN_AND_ELDERLY,
        health_factors=[HealthFactor.ASTHMA, HealthFactor.HEART],
        commute=CommuteMode.TWO_WHEELER,
        cooking_fuel=CookingFuel.LPG,
        budget=BudgetTier.VERY_LOW,
    )
    assert req.location == "Delhi NCR"
    assert req.aqi == 280
    assert req.household == HouseholdType.CHILDREN_AND_ELDERLY
    assert len(req.health_factors) == 2


@pytest.mark.parametrize("invalid_aqi", [-1, -50, 501, 1000])
def test_plan_request_invalid_aqi_rejected(invalid_aqi):
    """Verify out-of-range AQI values (-1, 501, etc.) are strictly rejected."""
    with pytest.raises(ValidationError) as exc_info:
        PlanRequest(
            location="Delhi",
            aqi=invalid_aqi,
            household=HouseholdType.ADULTS,
            commute=CommuteMode.CAR,
            cooking_fuel=CookingFuel.LPG,
            budget=BudgetTier.MODERATE,
        )
    errors = str(exc_info.value)
    assert "aqi" in errors


def test_plan_request_boundary_aqi_accepted():
    """Verify lower (0) and upper (500) AQI boundaries are valid."""
    req_0 = PlanRequest(
        location="City",
        aqi=0,
        household=HouseholdType.ADULTS,
        commute=CommuteMode.CAR,
        cooking_fuel=CookingFuel.LPG,
        budget=BudgetTier.MODERATE,
    )
    assert req_0.aqi == 0

    req_500 = PlanRequest(
        location="City",
        aqi=500,
        household=HouseholdType.ADULTS,
        commute=CommuteMode.CAR,
        cooking_fuel=CookingFuel.LPG,
        budget=BudgetTier.MODERATE,
    )
    assert req_500.aqi == 500


def test_plan_request_oversized_location_rejected():
    """Verify location length limits (max 80 chars, min 1 char)."""
    # 80 chars -> valid
    req_80 = PlanRequest(
        location="A" * 80,
        aqi=100,
        household=HouseholdType.ADULTS,
        commute=CommuteMode.CAR,
        cooking_fuel=CookingFuel.LPG,
        budget=BudgetTier.MODERATE,
    )
    assert len(req_80.location) == 80

    # 81 chars -> rejected
    with pytest.raises(ValidationError) as exc_info:
        PlanRequest(
            location="A" * 81,
            aqi=100,
            household=HouseholdType.ADULTS,
            commute=CommuteMode.CAR,
            cooking_fuel=CookingFuel.LPG,
            budget=BudgetTier.MODERATE,
        )
    assert "location" in str(exc_info.value)

    # Empty string or whitespace-only -> rejected
    with pytest.raises(ValidationError):
        PlanRequest(
            location="   ",
            aqi=100,
            household=HouseholdType.ADULTS,
            commute=CommuteMode.CAR,
            cooking_fuel=CookingFuel.LPG,
            budget=BudgetTier.MODERATE,
        )


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("household", "aliens"),
        ("household", "students"),
        ("commute", "helicopter"),
        ("commute", "teleport"),
        ("cooking_fuel", "coal_furnace"),
        ("cooking_fuel", "kerosene"),
        ("budget", "unlimited"),
        ("budget", "free"),
    ],
)
def test_plan_request_unknown_enum_values_rejected(field, bad_value):
    """Verify unknown or unlisted enum values are rejected with ValidationError."""
    payload = {
        "location": "Mumbai",
        "aqi": 120,
        "household": "adults",
        "health_factors": [],
        "commute": "car",
        "cooking_fuel": "lpg",
        "budget": "moderate",
    }
    payload[field] = bad_value
    with pytest.raises(ValidationError) as exc_info:
        PlanRequest(**payload)
    assert field in str(exc_info.value)


def test_plan_request_unknown_health_factor_rejected():
    """Verify unknown health factor strings are rejected."""
    payload = {
        "location": "Mumbai",
        "aqi": 120,
        "household": "adults",
        "health_factors": ["unknown_condition"],
        "commute": "car",
        "cooking_fuel": "lpg",
        "budget": "moderate",
    }
    with pytest.raises(ValidationError) as exc_info:
        PlanRequest(**payload)
    assert "health_factors" in str(exc_info.value)


def test_plan_request_extra_fields_rejected():
    """Verify PlanRequest rejects unrecognized extra fields (extra='forbid')."""
    payload = {
        "location": "Delhi",
        "aqi": 150,
        "household": "adults",
        "health_factors": [],
        "commute": "car",
        "cooking_fuel": "lpg",
        "budget": "moderate",
        "injection_payload": "DROP TABLE users;",
        "role": "admin",
    }
    with pytest.raises(ValidationError) as exc_info:
        PlanRequest(**payload)
    assert "extra" in str(exc_info.value).lower() or "injection_payload" in str(exc_info.value)


def test_plan_response_requires_min_three_items():
    """Verify PlanResponse enforces at least 3 items in every section."""
    item = ActionItem(action="Action", why="Why", impact="Roughly 50% test basis")

    with pytest.raises(ValidationError):
        PlanResponse(
            aqi_band="Severe",
            summary="Summary text",
            routine=[item, item],  # only 2 items
            indoor=[item, item, item],
            swaps=[item, item, item],
        )


def test_coords_query_validation():
    """Verify CoordsQuery handles boundaries, invalid ranges, NaN/inf, and extra fields."""
    # Valid
    q = CoordsQuery(lat=28.6139, lon=77.2090)
    assert q.lat == 28.6139
    assert q.lon == 77.2090

    # Latitude out of bounds
    with pytest.raises(ValidationError):
        CoordsQuery(lat=90.1, lon=0.0)
    with pytest.raises(ValidationError):
        CoordsQuery(lat=-90.1, lon=0.0)

    # Longitude out of bounds
    with pytest.raises(ValidationError):
        CoordsQuery(lat=0.0, lon=180.1)
    with pytest.raises(ValidationError):
        CoordsQuery(lat=0.0, lon=-180.1)

    # NaN and Inf
    with pytest.raises(ValidationError):
        CoordsQuery(lat=float("nan"), lon=77.0)
    with pytest.raises(ValidationError):
        CoordsQuery(lat=28.0, lon=float("inf"))

    # Extra fields rejected
    with pytest.raises(ValidationError):
        CoordsQuery(lat=28.61, lon=77.20, unauthorized="key")
