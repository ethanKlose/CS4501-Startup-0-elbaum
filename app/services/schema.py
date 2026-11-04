"""Strict shape of an LLM-produced plan. Anything that doesn't parse never reaches the user."""
from typing import List

from pydantic import BaseModel, Field, field_validator

from app.services.types import SECTIONS, SLOTS


class IngredientIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    quantity: float = Field(gt=0, allow_inf_nan=False)
    unit: str = Field(default="", max_length=20)
    section: str = "other"
    cost: float = Field(ge=0, allow_inf_nan=False)

    @field_validator("section")
    @classmethod
    def _section(cls, v):
        v = (v or "other").lower().strip()
        return v if v in SECTIONS else "other"


class MealIn(BaseModel):
    day: int = Field(ge=0, le=6)
    slot: str
    name: str = Field(min_length=1, max_length=120)
    cook_minutes: int = Field(ge=0, le=600)
    calories: int = Field(ge=0, le=5000)
    protein: float = Field(ge=0, le=500, allow_inf_nan=False)
    cost: float = Field(ge=0, allow_inf_nan=False)
    steps: List[str] = Field(min_length=1)
    ingredients: List[IngredientIn] = Field(min_length=1)

    @field_validator("slot")
    @classmethod
    def _slot(cls, v):
        v = v.lower().strip()
        if v not in SLOTS:
            raise ValueError(f"slot must be one of {SLOTS}")
        return v


class PlanIn(BaseModel):
    meals: List[MealIn]


def parse_plan(raw) -> "tuple[dict, list]":
    """Returns (normalized_plan_dict, errors). errors is empty on success."""
    from pydantic import ValidationError

    try:
        return PlanIn.model_validate(raw).model_dump(), []
    except ValidationError as e:
        errs = []
        for err in e.errors()[:10]:
            loc = ".".join(str(x) for x in err["loc"])
            errs.append(f"Invalid plan format at '{loc}': {err['msg']}")
        return {}, errs
    except Exception as e:  # not a dict, etc.
        return {}, [f"Plan was not valid JSON of the required shape: {e}"]
