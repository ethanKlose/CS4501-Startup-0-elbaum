from dataclasses import dataclass, field
from typing import Dict, List, Optional

SLOTS = ["breakfast", "lunch", "dinner"]
SECTIONS = ["produce", "dairy", "meat", "seafood", "bakery", "pantry", "frozen", "other"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@dataclass
class DayCtx:
    weekday: int
    minutes: int  # total cooking minutes available that day
    busy: bool = False
    skipped: bool = False  # e.g. eating out: no meals planned


@dataclass
class PlanContext:
    """Everything the LLM needs, and everything the validators check against."""

    budget: float
    days: List[DayCtx]
    restrictions: List[str] = field(default_factory=list)
    excluded: List[str] = field(default_factory=list)  # ingredients from free-text preferences
    goal: str = "none"
    calorie_target: Optional[int] = None
    free_text: str = ""
    pantry: List[Dict] = field(default_factory=list)  # {name, quantity, unit}
    pinned: List[Dict] = field(default_factory=list)  # full meal dicts that must be kept as-is
    liked: List[str] = field(default_factory=list)  # meal names rated highly before
    disliked: List[str] = field(default_factory=list)
    leftovers: List[str] = field(default_factory=list)  # ingredient names to use up
    avoid: List[str] = field(default_factory=list)  # meal names that felt repetitive last week
    prep_style: str = "auto"
    prep_days: List[int] = field(default_factory=list)
    prep_minutes: int = 120
    week_start: Optional[str] = None
    allow_pre_week: bool = True
    equipment: Optional[List[str]] = None
    cooking_skill: str = "any"
    allow_freezer: bool = True
    external_slots: List[Dict] = field(default_factory=list)
    cooking_windows: Dict = field(default_factory=dict)
    meal_times: Dict = field(default_factory=dict)
    earliest_day: int = -1
    earliest_minute: int = 0
    price_offers: Dict = field(default_factory=dict)
    checkout_budget: bool = False
    seed: int = 0

    def active_days(self) -> List[DayCtx]:
        return [d for d in self.days if not d.skipped]

    def slots_for(self, weekday):
        external={(m['day'],m['slot']) for m in self.external_slots}
        return [s for s in SLOTS if (weekday,s) not in external]
