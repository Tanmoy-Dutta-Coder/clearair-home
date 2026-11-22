import pytest

from app.schemas import BudgetTier, CommuteMode, CookingFuel, HouseholdType, PlanRequest


@pytest.fixture
def valid_request():
    return PlanRequest(
        location="Delhi",
        aqi=250,
        household=HouseholdType.ADULTS,
        commute=CommuteMode.CAR,
        cooking_fuel=CookingFuel.LPG,
        budget=BudgetTier.MODERATE,
    )
