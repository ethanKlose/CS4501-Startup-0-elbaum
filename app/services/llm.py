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
from app.services.schedule import capacities, storage_days
from app.services.types import SLOTS, WEEKDAYS, PlanContext
from app.services.validators import HIGH_PROTEIN_DAILY_G, SOFT_CHECKS, schedule_for

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
        """Pick meals ignoring *when* they are cooked, schedule the cooking, and judge the result by every soft goal
        (cooking time, calories, protein). If it isn't clean, weigh cooking time differently or re-roll the dice,
        and keep the best candidate seen."""
        best = None
        for reroll in range(3):
            for lam in (0.0, 0.03, 0.08, 0.2, 0.5):
                plan = self._pick(ctx, lam, ctx.seed + reroll * 7919)
                issues = [w for check in SOFT_CHECKS for w in check(plan, ctx)]
                sched = schedule_for(plan, ctx)
                over = sum(u - cap for u, cap in sched.overbooked.values())
                days = {}
                for m in plan["meals"]:
                    days[m["day"]] = days.get(m["day"], 0) + m["calories"]
                dev = abs(sum(days.values()) / max(len(days), 1) - ctx.calorie_target) if ctx.calorie_target else 0
                key = (len(issues), over, dev)
                if best is None or key < best[0]:
                    best = (key, plan)
                if not issues:
                    return plan
        return best[1]

    def _pick(self, ctx: PlanContext, lam: float, seed: int = 0) -> Dict:
        rng = random.Random(seed)
        caps = capacities(ctx.days, ctx.prep_style, ctx.prep_days, ctx.prep_minutes, ctx.allow_pre_week)
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
        times = Counter(m["name"] for m in meals)
        for m in meals:
            used.update(i["name"].lower() for i in m["ingredients"])
        spent = sum(m["cost"] for m in meals)
        open_slots = [(d.weekday, s) for d in ctx.active_days() for s in SLOTS if (d.weekday, s) not in pinned]
        slots_left = len(open_slots)
        target_cal = ctx.calorie_target

        def fresh_ok(r, day):  # fresh dishes can't be cooked days ahead, so their cook day needs spare time
            if storage_days(r) != 1:
                return True
            return caps.get(day, 0) >= r["cook_minutes"] or caps.get(day - 1, 0) >= r["cook_minutes"]

        active = ctx.active_days()
        for n_done, day in enumerate(active):
            todays = [m for m in meals if m["day"] == day.weekday]
            day_target = target_cal
            if target_cal:  # steer the weekly average: make up yesterday's shortfall (or overshoot) today, within reason
                so_far = sum(m["calories"] for m in meals if m["day"] != day.weekday)
                gap = (target_cal * n_done - so_far) / max(len(active) - n_done, 1)
                day_target = target_cal + max(-300, min(300, gap))
            open_today = [s for s in SLOTS if (day.weekday, s) not in pinned]
            if not open_today:
                continue
            future = slots_left - len(open_today)
            future_min = sum(min_cost[s] for (_, s) in open_slots[len(open_slots) - future:]) if future else 0
            hard_cap = ctx.budget - spent - future_min
            soft = (ctx.budget - spent) / max(slots_left, 1) * len(open_today)

            sc: Dict[str, float] = {}
            for r in allowed:
                ings = [i["name"].lower() for i in r["ingredients"]]
                v = 2.0 * sum(i in pantry for i in ings) + 1.5 * sum(i in leftovers for i in ings)
                v += 0.8 * sum(1 for i in ings if used[i] > 0)
                v += 3.0 if r["name"] in ctx.liked else 0
                v -= 2.5 if r["name"] in ctx.avoid else 0
                n = times[r["name"]]  # a little repetition batches well; a lot is boring
                v += 0.8 if 1 <= n <= 3 else (-2.5 * (n - 3) if n > 3 else 0)
                v += rng.random() * 1.2
                if ctx.goal == "high_protein":
                    v += r["protein"] / 15
                if target_cal:
                    v -= abs(r["calories"] - target_cal / 3.0) / 100.0
                sc[r["name"]] = v - 0.25 * r["cost"] - lam * r["cook_minutes"]

            cands = []
            for slot in open_today:
                pool = [r for r in allowed if slot in r["slots"]]
                pool = [r for r in pool if fresh_ok(r, day.weekday)] or pool
                cands.append(sorted(pool, key=lambda r: sc[r["name"]], reverse=True)[:8])
            best, best_val = None, None
            base_cal = sum(m["calories"] for m in todays)
            base_pro = sum(m["protein"] for m in todays)
            for combo in itertools.product(*cands):
                c = sum(r["cost"] for r in combo)
                if c > hard_cap:
                    continue
                val = sum(sc[r["name"]] for r in combo) - max(0.0, c - soft) * 1.5
                if len({r["name"] for r in combo}) < len(combo):
                    val -= 3.0  # same dish twice in one day
                cal = base_cal + sum(r["calories"] for r in combo)
                pro = base_pro + sum(r["protein"] for r in combo)
                if target_cal:
                    val -= abs(cal - day_target) / 70.0
                if ctx.goal == "high_protein":
                    val -= max(0.0, HIGH_PROTEIN_DAILY_G + 15 - pro) / 8.0
                if best_val is None or val > best_val:
                    best, best_val = combo, val
            if best is None:  # budget infeasible: return the cheapest anyway; the validators will reject it
                best = tuple(min(pool, key=lambda r: r["cost"]) for pool in cands if pool)
            for slot, r in zip(open_today, best):
                m = _recipe_to_meal(r, day.weekday, slot)
                meals.append(m)
                spent += m["cost"]
                used.update(i["name"].lower() for i in m["ingredients"])
                times[m["name"]] += 1
            slots_left -= len(open_today)
        return {"meals": meals}


def _day(ctx: PlanContext, weekday: int):
    return next(d for d in ctx.days if d.weekday == weekday)


# ----------------------------------------------------------------------------- real

SYSTEM = """You are the planning engine of PlateJoy, a weekly meal planner for university students.
Return ONLY a JSON object (no prose, no markdown fences) of the form:
{"meals": [{"day": 0-6 (0=Monday), "slot": "breakfast"|"lunch"|"dinner", "name": str, "cook_minutes": int,
  "calories": int, "protein": number (grams), "cost": number (USD, must equal the sum of ingredient costs),
  "steps": [str], "ingredients": [{"name": str, "quantity": number, "unit": str,
  "section": "produce"|"dairy"|"meat"|"seafood"|"bakery"|"pantry"|"frozen"|"other", "cost": number}]}]}

HARD rules (a plan breaking any of these is thrown away):
- exactly one meal per slot per active day; skipped days get no meals;
- the sum of all ingredient costs must not exceed the weekly budget;
- never use an ingredient that violates a restriction or an excluded ingredient;
- keep pinned meals exactly as given; do not use the disliked meal names.

BEST-EFFORT goals (misses are shown to the user as warnings, so try hard):
- hit the calorie target (weekly average within 10%, each day within 30%) or the protein goal;
- prefer meals that share ingredients and use pantry items and leftovers first.

You choose WHAT to eat, not WHEN to cook. A separate scheduler decides the cook day for every meal, so a busy
day does NOT mean fewer meals. Rules of thumb that make the schedule work:
- cook_minutes is the active time to cook ONE batch of the dish; reheating is free and not counted.
- Repeating a dish 2-4 times a week is encouraged: the scheduler cooks it once in a batch and reheats it.
- Fresh foods (salads, sandwiches, wraps, toast, smoothies, scrambles) are made close to eating; do not rely on
  batching them. Fish keeps 2 days in the fridge, other proteins 4, then the freezer.
- cook_capacity_minutes shows how many minutes of cooking fit on each day (-1 = the Sunday before the week).
  Keep the total cooking within it, favouring no-cook (cook_minutes 0) meals when capacity is very low.
If feedback from a previous attempt is given, fix every item in it."""


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
        caps = capacities(ctx.days, ctx.prep_style, ctx.prep_days, ctx.prep_minutes, ctx.allow_pre_week)
        payload = {"context": asdict(ctx), "cook_capacity_minutes": {str(k): v for k, v in sorted(caps.items())},
                   "feedback_from_previous_attempt": list(feedback)}
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
    if settings.anthropic_api_key.strip():
        return AnthropicLLM(settings.anthropic_api_key, settings.anthropic_model)
    return FakeLLM()
