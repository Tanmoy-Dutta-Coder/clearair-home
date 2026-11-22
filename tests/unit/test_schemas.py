import pytest
from pydantic import ValidationError

from app.schemas import (
    BudgetTier,
    CommuteMode,
    CookingFuel,
    CoordsQuery,
    HouseholdType,
    PlanRequest,
)


@pytest.mark.unit
def test_plan_request_strips_location_and_accepts_boundaries():
    from app.schemas import PlanRequest

    for aqi in (0, 500):
        request = PlanRequest(
            location="  Delhi  ",
            aqi=aqi,
            household="adults",
            commute="car",
            cooking_fuel="lpg",
            budget="moderate",
        )
        assert request.location == "Delhi"
        assert request.aqi == aqi


@pytest.mark.unit
@pytest.mark.parametrize(
    "field,value",
    [
        ("household", "invalid"),
        ("health_factors", ["invalid"]),
        ("commute", "invalid"),
        ("cooking_fuel", "invalid"),
        ("budget", "invalid"),
    ],
)
def test_plan_request_rejects_invalid_enum_values(field, value):
    payload = dict(
        location="Delhi",
        aqi=100,
        household="adults",
        health_factors=[],
        commute="car",
        cooking_fuel="lpg",
        budget="moderate",
    )
    payload[field] = value
    with pytest.raises(ValidationError):
        PlanRequest(**payload)


@pytest.mark.unit
@pytest.mark.parametrize("location", ["", "   ", "x" * 81])
def test_plan_request_rejects_empty_or_overlong_location(location):
    with pytest.raises(ValidationError):
        PlanRequest(
            location=location,
            aqi=100,
            household=HouseholdType.ADULTS,
            commute=CommuteMode.CAR,
            cooking_fuel=CookingFuel.LPG,
            budget=BudgetTier.MODERATE,
        )


@pytest.mark.unit
def test_plan_request_rejects_extra_fields():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PlanRequest(
            location="Delhi",
            aqi=100,
            household="adults",
            commute="car",
            cooking_fuel="lpg",
            budget="moderate",
            extra="x",
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    "lat,lon",
    [(90.01, 0), (-90.01, 0), (0, 180.01), (0, float("nan")), (float("inf"), 0)],
)
def test_coords_query_rejects_out_of_range_or_nonfinite_values(lat, lon):
    with pytest.raises(ValidationError):
        CoordsQuery(lat=lat, lon=lon)
