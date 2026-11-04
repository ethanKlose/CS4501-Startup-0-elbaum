"""LLM access. Two interchangeable clients:

* FakeLLM      - deterministic, offline, catalog-based. Used when no API key is set and in tests.
* AnthropicLLM - the real thing. Only needs ANTHROPIC_API_KEY in .env.

Both implement:
    generate_plan(ctx: PlanContext, feedback: list[str]) -> dict   (raw, UNVALIDATED plan)
    interpret_preferences(text: str) -> dict                       ({"excluded": [...], "day_minutes_cap": {"0": 15}})
"""
import itertools
import json
import random
import re
from collections import Counter
from dataclasses import asdict
from typing import Dict, List

from app.config import settings
from app.services.catalog import RECIPES
from app.services.diet import meal_violations
from app.services.types import SLOTS, WEEKDAYS, PlanContext

# ----------------------------------------------------------------------------- fake


def _recipe_to_meal(r: dict, day: int, slot: str) -> dict:
    m = {k: v for k, v in r.items() if k != "slots"}
    m = json.loads(json.dumps(m))
    m.update(day=day, slot=slot)
    return m


_STOP = {"cooking", "cook", "time", "more", "too", "much", "spicy", "a", "the", "any", "all", "eating", "to", "of", "that", "it", "i", "me", "my"}
_TRIGGER = re.compile(r"\b(?:no|without|avoid|skip|hate|dislike|allergic to|allergy to|cannot eat|can't eat|don't eat|do not eat|don't like|do not like|not a fan of|never)\s+(.+)", re.I)


class FakeLLM:
    name = "fake"

    # -- preference interpretation ------------------------------------------------------
    def interpret_preferences(self, text: str) -> Dict:
        excluded: List[str] = []
        caps: Dict[str, int] = {}
        for clause in re.split(r"[.;\n,]+", text or ""):
            clause_l = clause.strip().lower()
            if not clause_l:
                continue
            days = [i for i, d in enumerate(WEEKDAYS) if d.lower() in clause_l or d.lower()[:3] + "s" in clause_l]
            if "cook" in clause_l and days:
                cap = 0 if re.search(r"\bno cooking\b|\bnot cook|\bcan't cook|\bcannot cook", clause_l) else 15
                for d in days:
                    caps[str(d)] = cap
                continue
            m = _TRIGGER.search(clause_l)
            if m:
                for item in re.split(r"\band\b|/|&", m.group(1)):
                    words = [w for w in re.findall(r"[a-z-]+", item) if w not in _STOP]
                    if words:
                        excluded.append(" ".join(words))
        return {"excluded": sorted(set(excluded)), "day_minutes_cap": caps}

    # -- plan generation ----------------------------------------------------------------
    def generate_plan(self, ctx: PlanContext, feedback=()) -> Dict:
        rng = random.Random(ctx.seed)
        pinned = {(m["day"], m["slot"]): m for m in ctx.pinned}
        pantry = {p["name"].lower() for p in ctx.pantry}
        leftovers = {x.lower() for x in ctx.leftovers}
        allowed = [
            r for r in RECIPES
            if not meal_violations(r, ctx.restrictions, ctx.excluded) and r["name"] not in ctx.disliked
        ]
        min_cost = {s: min([r["cost"] for r in allowed if s in r["slots"]] or [0]) for s in SLOTS}

        meals: List[dict] = [m for m in ctx.pinned if not _day(ctx, m["day"]).skipped]
        used = Counter()
        for m in meals:
            used.update(i["name"].lower() for i in m["ingredients"])
        spent = sum(m["cost"] for m in meals)
        open_slots = [(d.weekday, s) for d in ctx.active_days() for s in SLOTS if (d.weekday, s) not in pinned]
        slots_left = len(open_slots)
        target_cal = ctx.calorie_target

        for day in ctx.active_days():
            todays = [m for m in meals if m["day"] == day.weekday]
            minutes_left = day.minutes - sum(m["cook_minutes"] for m in todays)
            open_today = [s for s in SLOTS if (day.weekday, s) not in pinned]
            if not open_today:
                continue
            future = slots_left - len(open_today)
            future_min = sum(min_cost[s] for (_, s) in open_slots[len(open_slots) - future:]) if future else 0
            hard_cap = ctx.budget - spent - future_min
            soft = (ctx.budget - spent) / max(slots_left, 1) * len(open_today)

            def score(r):
                ings = [i["name"].lower() for i in r["ingredients"]]
                s = 2.0 * sum(i in pantry for i in ings) + 1.5 * sum(i in leftovers for i in ings)
                s += 0.8 * sum(1 for i in ings if used[i] > 0)
                s += 3.0 if r["name"] in ctx.liked else 0
                s += rng.random() * 1.2
                if ctx.goal == "high_protein":
                    s += r["protein"] / 15
                return s - 0.25 * r["cost"]

            cands = []
            for slot in open_today:
                pool = sorted((r for r in allowed if slot in r["slots"]), key=score, reverse=True)[:7]
                cands.append(pool)
            best, best_val = None, None
            base_cal = sum(m["calories"] for m in todays)
            base_pro = sum(m["protein"] for m in todays)
            for combo in itertools.product(*cands):
                t = sum(r["cook_minutes"] for r in combo)
                c = sum(r["cost"] for r in combo)
                if t > minutes_left or c > hard_cap:
                    continue
                val = sum(score(r) for r in combo) - max(0.0, c - soft) * 1.5
                cal = base_cal + sum(r["calories"] for r in combo)
                pro = base_pro + sum(r["protein"] for r in combo)
                if target_cal:
                    val -= abs(cal - target_cal) / 120.0
                if ctx.goal == "high_protein":
                    val -= max(0.0, 100 - pro) / 8.0
                if best_val is None or val > best_val:
                    best, best_val = combo, val
            if best is None:  # infeasible: return the cheapest/shortest anyway; validators will reject it
                best = tuple(min(pool, key=lambda r: (r["cook_minutes"], r["cost"])) if pool else None for pool in cands)
                best = tuple(b for b in best if b)
            for slot, r in zip(open_today, best):
                m = _recipe_to_meal(r, day.weekday, slot)
                meals.append(m)
                spent += m["cost"]
                used.update(i["name"].lower() for i in m["ingredients"])
                minutes_left -= m["cook_minutes"]
            slots_left -= len(open_today)
        return {"meals": meals}


def _day(ctx: PlanContext, weekday: int):
    return next(d for d in ctx.days if d.weekday == weekday)


# ----------------------------------------------------------------------------- real

SYSTEM = f"""You are the planning engine of PlateJoy, a weekly meal planner for university students.
Return ONLY a JSON object (no prose, no markdown fences) of the form:
{{"meals": [{{"day": 0-6 (0=Monday), "slot": "breakfast"|"lunch"|"dinner", "name": str, "cook_minutes": int,
  "calories": int, "protein": number (grams), "cost": number (USD, must equal the sum of ingredient costs),
  "steps": [str], "ingredients": [{{"name": str, "quantity": number, "unit": str,
  "section": "produce"|"dairy"|"meat"|"seafood"|"bakery"|"pantry"|"frozen"|"other", "cost": number}}]}}]}}
Hard rules: exactly one meal per slot per active day; skipped days get no meals; the sum of all meal costs must not
exceed the budget; the sum of cook_minutes per day must not exceed that day's minutes; never use an ingredient that
violates a restriction or excluded ingredient; keep pinned meals exactly as given. Prefer meals that share
ingredients, use the pantry/leftovers first, and fit the goal. If feedback lists errors from a previous attempt, fix all of them."""


def _extract_json(text: str):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start : end + 1])


class AnthropicLLM:
    name = "anthropic"

    def __init__(self, api_key: str, model: str):
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def _ask(self, system: str, user: str, max_tokens: int):
        resp = self.client.messages.create(
            model=self.model, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": user}]
        )
        return _extract_json("".join(b.text for b in resp.content if getattr(b, "type", "") == "text"))

    def generate_plan(self, ctx: PlanContext, feedback=()) -> Dict:
        payload = {"context": asdict(ctx), "feedback_from_previous_attempt": list(feedback)}
        return self._ask(SYSTEM, json.dumps(payload), 12000)

    def interpret_preferences(self, text: str) -> Dict:
        if not (text or "").strip():
            return {"excluded": [], "day_minutes_cap": {}}
        system = (
            'Extract structured constraints from a student\'s free-text meal preferences. Return ONLY JSON: '
            '{"excluded": [ingredient or food-group words to never serve, e.g. "fish"], '
            '"day_minutes_cap": {"<weekday 0=Mon..6=Sun>": max cooking minutes that day}}. '
            'Use 15 for "hate cooking" and 0 for "no cooking".'
        )
        try:
            out = self._ask(system, text, 500)
            return {"excluded": [str(x) for x in out.get("excluded", [])],
                    "day_minutes_cap": {str(k): int(v) for k, v in out.get("day_minutes_cap", {}).items()}}
        except Exception:
            return FakeLLM().interpret_preferences(text)


# ----------------------------------------------------------------------------- selection

def get_llm():
    """FastAPI dependency. Override in tests via app.dependency_overrides[get_llm]."""
    if settings.anthropic_api_key:
        return AnthropicLLM(settings.anthropic_api_key, settings.anthropic_model)
    return FakeLLM()
