"""Pydantic request and response schemas for clearair-home."""

import math
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


class HouseholdType(str, Enum):
    """Household demographic composition."""

    ADULTS = "adults"
    YOUNG_CHILDREN = "young_children"
    ELDERLY = "elderly"
    CHILDREN_AND_ELDERLY = "children_and_elderly"


class HealthFactor(str, Enum):
    """Specific health vulnerabilities and risk factors."""

    ASTHMA = "asthma"
    HEART = "heart"
    PREGNANCY = "pregnancy"
    OUTDOOR_WORK = "outdoor_work"


class CommuteMode(str, Enum):
    """Primary mode of daily commuting."""

    CAR = "car"
    TWO_WHEELER = "two_wheeler"
    PUBLIC_TRANSPORT = "public_transport"
    WALK_CYCLE = "walk_cycle"
    WORK_FROM_HOME = "work_from_home"


class CookingFuel(str, Enum):
    """Primary cooking fuel used in the household."""

    LPG = "lpg"
    INDUCTION = "induction"
    BIOMASS = "biomass"
    PIPED_GAS = "piped_gas"


class BudgetTier(str, Enum):
    """Household budget constraint for air quality solutions."""

    VERY_LOW = "very_low"
    MODERATE = "moderate"
    FLEXIBLE = "flexible"


class PlanRequest(BaseModel):
    """Validated input context for generating an air quality adaptation plan."""

    model_config = ConfigDict(extra="forbid")

    location: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    aqi: int = Field(..., ge=0, le=500, description="Indian Air Quality Index value (0 to 500)")
    household: HouseholdType
    health_factors: list[HealthFactor] = Field(
        default_factory=list, description="List of pre-existing health vulnerabilities"
    )
    commute: CommuteMode
    cooking_fuel: CookingFuel
    budget: BudgetTier


class ActionItem(BaseModel):
    """A specific recommendation item with justification and hedged impact."""

    model_config = ConfigDict(extra="forbid")

    action: str = Field(..., min_length=1, description="Concise, actionable recommendation")
    why: str = Field(..., min_length=1, description="Contextual rationale tailored to user situation")
    impact: str = Field(..., min_length=1, description="Honest, hedged estimate with an explicit basis")


class PlanResponse(BaseModel):
    """Complete air quality adaptation plan produced deterministically or personalized with AI."""

    model_config = ConfigDict(extra="forbid")

    aqi_band: str = Field(..., min_length=1, description="CPCB Indian AQI category name")
    summary: str = Field(
        ...,
        min_length=1,
        description="Overview summary of current air risk and guidance focus",
    )
    routine: list[ActionItem] = Field(
        ...,
        min_length=3,
        description="Daily timing, transit, and exposure routine recommendations",
    )
    indoor: list[ActionItem] = Field(
        ...,
        min_length=3,
        description="Indoor air quality interventions, filtration, and ventilation hacks",
    )
    swaps: list[ActionItem] = Field(
        ...,
        min_length=3,
        description="Sustainable daily alternatives for cooking, commuting, and habit change",
    )
    used_ai: bool = Field(
        default=False,
        description="Flag indicating whether Gemini AI was used to personalise the plan",
    )


class CoordsQuery(BaseModel):
    """Query model for coordinate-based AQI auto-detection."""

    model_config = ConfigDict(extra="forbid")

    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude between -90 and 90")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude between -180 and 180")

    @field_validator("lat", "lon")
    @classmethod
    def validate_finite(cls, v: float) -> float:
        """Reject non-finite float values such as NaN or Infinity."""
        if not math.isfinite(v):
            raise ValueError("Coordinates must be finite numbers (no NaN or inf)")
        return v
