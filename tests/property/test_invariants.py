import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from app.aqi_provider import pm_to_indian_aqi
from app.rules import aqi_band, build_plan
from app.schemas import BudgetTier, CommuteMode, CookingFuel, HouseholdType, PlanRequest

pytestmark = pytest.mark.property


@st.composite
def valid_plan_requests(draw):
    return PlanRequest(
        location=draw(st.text(min_size=1, max_size=80).filter(lambda value: value.strip())),
        aqi=draw(st.integers(min_value=0, max_value=500)),
        household=draw(st.sampled_from(list(HouseholdType))),
        health_factors=[],
        commute=draw(st.sampled_from(list(CommuteMode))),
        cooking_fuel=draw(st.sampled_from(list(CookingFuel))),
        budget=draw(st.sampled_from(list(BudgetTier))),
    )


@settings(max_examples=40, deadline=None)
@given(valid_plan_requests())
def test_build_plan_never_raises_and_returns_complete_sections(request):
    plan = build_plan(request)
    assert len(plan.routine) >= 3
    assert len(plan.indoor) >= 3
    assert len(plan.swaps) >= 3


@settings(max_examples=30, deadline=None)
@given(valid_plan_requests())
def test_build_plan_is_deterministic_for_identical_request(request):
    assert build_plan(request) == build_plan(request)


@settings(max_examples=30, deadline=None)
@given(st.integers(min_value=0, max_value=500), st.integers(min_value=0, max_value=500))
def test_aqi_band_does_not_improve_as_aqi_rises(first, second):
    if first <= second:
        order = {
            "Good": 0,
            "Satisfactory": 1,
            "Moderate": 2,
            "Poor": 3,
            "Very Poor": 4,
            "Severe": 5,
        }
        assert order[aqi_band(first)] <= order[aqi_band(second)]


@settings(max_examples=40, deadline=None)
@given(
    st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False),
)
def test_pm_aqi_is_bounded_and_monotonic_when_one_pollutant_increases(pm25, pm10):
    value = pm_to_indian_aqi(pm25, pm10)
    assert 0 <= value <= 500
    assert value <= pm_to_indian_aqi(pm25 + 0.01, pm10)
    assert value <= pm_to_indian_aqi(pm25, pm10 + 0.01)


@settings(max_examples=30, deadline=None)
@given(st.integers(min_value=-10000, max_value=-1) | st.integers(min_value=501, max_value=10000))
def test_plan_schema_rejects_out_of_range_aqi(aqi):
    with pytest.raises(ValidationError):
        PlanRequest(
            location="Delhi",
            aqi=aqi,
            household="adults",
            commute="car",
            cooking_fuel="lpg",
            budget="moderate",
        )
