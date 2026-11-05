from collections import Counter
from app.services.grocery import norm
from typing import Dict, Iterable


def sharing_stats(meals: Iterable[dict]) -> Dict:
    """How much do meals overlap in ingredients? Lower distinct/lines = more sharing = less waste."""
    meals = list(meals)
    meals_per_ingredient = Counter()
    for m in meals:
        for name in {norm(i["name"]) for i in m["ingredients"]}:
            meals_per_ingredient[name] += 1
    lines = sum(meals_per_ingredient.values())
    shared = sorted(n for n, c in meals_per_ingredient.items() if c >= 2)
    return dict(distinct=len(meals_per_ingredient), lines=lines, shared=shared,
                ratio=round(len(meals_per_ingredient) / lines, 3) if lines else 0)
