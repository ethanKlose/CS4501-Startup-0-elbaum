"""Strict shape of an LLM-produced plan. Anything that doesn't parse never reaches the user."""
from typing import List, Annotated

from pydantic import BaseModel, Field, field_validator

from app.services.types import SECTIONS, SLOTS


def nonblank(value):
    value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    return value


class IngredientIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    quantity: float = Field(gt=0, le=1_000_000, allow_inf_nan=False)
    unit: str = Field(default="", max_length=20)
    section: str = "other"
    cost: float = Field(ge=0, le=1_000_000, allow_inf_nan=False)

    _name = field_validator("name")(nonblank)

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
    cost: float = Field(ge=0, le=1_000_000, allow_inf_nan=False)
    steps: List[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(min_length=1, max_length=30)
    ingredients: List[IngredientIn] = Field(min_length=1, max_length=50)

    _name = field_validator("name")(nonblank)

    @field_validator("steps")
    @classmethod
    def _steps(cls, values):
        return [nonblank(v) for v in values]

    @field_validator("slot")
    @classmethod
    def _slot(cls, v):
        v = v.lower().strip()
        if v not in SLOTS:
            raise ValueError(f"slot must be one of {SLOTS}")
        return v


class PlanIn(BaseModel):
    meals: List[MealIn] = Field(max_length=21)


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
