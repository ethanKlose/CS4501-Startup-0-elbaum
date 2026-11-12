"""LLM access. Two interchangeable clients:

* FakeLLM      - deterministic, offline, catalog-based. Used when no API key is set and in tests.
* AnthropicLLM / OpenAILLM - the real thing. Need ANTHROPIC_API_KEY or OPENAI_API_KEY in .env.

Both implement:
    generate_plan(ctx: PlanContext, feedback: list[str]) -> dict   (raw, UNVALIDATED plan)
    interpret_preferences(text: str) -> dict                       ({"excluded": [...], "day_minutes_cap": {"0": 15}})
"""
import itertools
import os
import time
import json
import random
import re
from collections import Counter
from dataclasses import asdict
from typing import Dict, List

from app.config import settings
from app.services.catalog import RECIPES
from app.services.diet import meal_violations
from app.services.lifestyle import violations as lifestyle_violations
from app.services.pricing import apply_recipe_prices
from app.services.schedule import capacities, storage_days
from app.services.types import SLOTS, WEEKDAYS, PlanContext
from app.services.nutrition_goals import protein_target
from app.services.validators import SOFT_CHECKS, schedule_for, check_checkout_budget, check_cooking_deadlines

# ----------------------------------------------------------------------------- fake


def _recipe_to_meal(r: dict, day: int, slot: str) -> dict:
    m = {k: v for k, v in r.items() if k != "slots"}
    m = json.loads(json.dumps(m))
    m.update(day=day, slot=slot)
    return m


def normalize_preferences(raw):
    if not isinstance(raw,dict):raise ValueError('Preference extraction must return an object.')
    excluded=raw.get('excluded',[]);caps=raw.get('day_minutes_cap',{})
    if not isinstance(excluded,list) or not isinstance(caps,dict):raise ValueError('Invalid preference fields.')
    terms=[x.strip().lower() for x in excluded if isinstance(x,str) and 0<len(x.strip())<=100][:40]
    cleaned={}
    for day,value in caps.items():
        if str(day) not in {str(i) for i in range(7)}:raise ValueError('Invalid weekday in preferences.')
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not 0<=value<=480:raise ValueError('Invalid cooking limit.')
        cleaned[str(day)]=int(value)
    return {'excluded':sorted(set(terms)),'day_minutes_cap':cleaned}


class FakeLLM:
    name = "fake"

    # -- preference interpretation ------------------------------------------------------
    def interpret_preferences(self, text: str) -> Dict:
        from app.services.preference_text import interpret
        return interpret(text)

    # -- plan generation ----------------------------------------------------------------
    def generate_plan(self, ctx: PlanContext, feedback=()) -> Dict:
        from app.services.planning_quality import improve_plan
        return improve_plan(self._generate(ctx, feedback), ctx, RECIPES)

    def _generate(self, ctx: PlanContext, feedback=()) -> Dict:
        """Pick meals ignoring *when* they are cooked, schedule the cooking, and judge the result by every soft goal
        (cooking time, calories, protein). If it isn't clean, weigh cooking time differently or re-roll the dice,
        and keep the best candidate seen."""
        best = None
        fallback_tried = False
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
                hard = check_checkout_budget(plan,ctx) + check_cooking_deadlines(plan,ctx)
                key = (len(hard), len(issues), over, dev)
                if best is None or key < best[0]:
                    best = (key, plan)
                if not hard and not issues:
                    return plan
            if reroll == 0 and best and check_checkout_budget(best[1],ctx):
                from app.services.budget_search import affordable_fallback
                fallback_tried = True
                fallback = affordable_fallback(ctx,RECIPES)
                if fallback is not None:return fallback
        if not fallback_tried and best and check_checkout_budget(best[1],ctx):
            from app.services.budget_search import affordable_fallback
            fallback=affordable_fallback(ctx,RECIPES)
            if fallback is not None:return fallback
        return best[1]

    def _pick(self, ctx: PlanContext, lam: float, seed: int = 0) -> Dict:
        rng = random.Random(seed)
        caps = capacities(ctx.days, ctx.prep_style, ctx.prep_days, ctx.prep_minutes, ctx.allow_pre_week)
        pinned = {(m["day"], m["slot"]): m for m in ctx.pinned}
        pantry = {p["name"].lower() for p in ctx.pantry}
        leftovers = {x.lower() for x in ctx.leftovers}
        allowed = [
            apply_recipe_prices(r,ctx.price_offers) for r in RECIPES
            if not meal_violations(r, ctx.restrictions, ctx.excluded) and not lifestyle_violations(r,ctx) and r["name"] not in ctx.disliked
        ]
        min_cost = {s: min([r["cost"] for r in allowed if s in r["slots"]] or [0]) for s in SLOTS}

        meals: List[dict] = [m for m in ctx.pinned if not _day(ctx, m["day"]).skipped]
        used = Counter()
        times = Counter(m["name"] for m in meals)
        for m in meals:
            used.update(i["name"].lower() for i in m["ingredients"])
        spent = sum(m["cost"] for m in meals)
        open_slots = [(d.weekday, s) for d in ctx.active_days() for s in ctx.slots_for(d.weekday) if (d.weekday, s) not in pinned]
        slots_left = len(open_slots)
        target_cal = ctx.calorie_target
        target_pro = protein_target(ctx)

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
            open_today = [s for s in ctx.slots_for(day.weekday) if (day.weekday, s) not in pinned]
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
                v += 0.35 * sum(1 for i in ings if used[i] > 0)
                v += 3.0 if r["name"] in ctx.liked else 0
                v -= 2.5 if r["name"] in ctx.avoid else 0
                n = times[r["name"]]  # a little repetition batches well; a lot is boring
                v += 1.2 if n == 0 else (-1.0 * n if n <= 3 else -3.5 * (n - 3))
                v += rng.random() * 1.2
                if target_pro is not None:
                    v += r["protein"] / 15
                if target_cal:
                    v -= abs(r["calories"] - target_cal / 3.0) / 100.0
                sc[r["name"]] = v - lam * r["cook_minutes"]

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
                if target_pro is not None:
                    val -= max(0.0, target_pro + 15 - pro) / 8.0
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
Choose only the approved recipe names for each required slot. Return ONLY JSON:
{"meals": [{"day": 0-6 (0=Monday), "slot": "breakfast"|"lunch"|"dinner", "name": "approved recipe name"}]}
The server supplies trusted ingredients, quantities, costs, steps and nutrients.
Do not invent recipes, edit portion sizes or supply your own nutrition values.

HARD rules (a plan breaking any of these is thrown away):
- exactly one meal per slot per active day: return every (day, slot) listed in required_meals, nothing
  missing, nothing extra (skipped days get no meals);
- the estimated shopping total after pantry deductions must not exceed the weekly budget;
  consider shopping_cost_once estimates and shared ingredients when checkout_budget is enabled;
  these per-dish estimates are not additive basket totals, and portion costs are not shopping totals;
- never use an ingredient that violates a restriction or an excluded ingredient;
- keep pinned meals exactly as given; do not use the disliked meal names.

BEST-EFFORT goals (misses are shown to the user as warnings, so try hard):
- satisfy ALL selected nutrition goals together, not one instead of another;
- hit the calorie target (weekly average within 10%, each day within 30%) AND, when selected,
  reach at least protein_target grams each day. A legacy high_protein goal with no protein_target means 75g/day;
- calorie_target is per DAY: the three meals of every day must add up to about that number (2000 kcal means
  ~650 per meal, not 300). Choose appropriately sized approved dishes to reach it;
- variety: aim for 3 breakfast choices, 3 lunch choices and 4 dinner choices when available;
  normally repeat a dish at most 3 times and at most 2 consecutive days. These are preferences, not rejection rules;
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


def _fix_costs(plan):
    """A meal's cost is, by definition, the sum of its ingredient costs. Models get this arithmetic wrong
    often, so we derive it instead of burning a retry on it."""
    try:
        for m in plan.get("meals", []):
            ings = m.get("ingredients") or []
            if ings:
                m["cost"] = round(sum(float(i.get("cost", 0)) for i in ings), 2)
    except (TypeError, ValueError, AttributeError):
        pass  # malformed output is left for the validators to report
    return plan


class AnthropicLLM:
    name = "anthropic"

    def __init__(self, api_key: str, model: str):
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key,timeout=float(os.environ.get("LLM_TIMEOUT_SECONDS","20")),max_retries=0)
        self.metrics = []
        self.model = model

    def _ask(self, system: str, user: str, max_tokens: int):
        started=time.perf_counter()
        resp = self.client.messages.create(
            model=self.model, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": user}]
        )
        usage=getattr(resp,'usage',None)
        metric={'latency_seconds':round(time.perf_counter()-started,3),'input_tokens':getattr(usage,'input_tokens',None),'output_tokens':getattr(usage,'output_tokens',None),'stop_reason':getattr(resp,'stop_reason',None)}
        if not hasattr(self,'metrics'):self.metrics=[]
        self.metrics.append(metric)
        return _extract_json("".join(b.text for b in resp.content if getattr(b, "type", "") == "text"))

    def generate_plan(self, ctx: PlanContext, feedback=()) -> Dict:
        caps = capacities(ctx.days, ctx.prep_style, ctx.prep_days, ctx.prep_minutes, ctx.allow_pre_week)
        payload = {"context": asdict(ctx), "cook_capacity_minutes": {str(k): v for k, v in sorted(caps.items())},
                   "feedback_from_previous_attempt": list(feedback)}
        from app.services.nutrition import catalog_plan
        from app.services.planning_quality import eligible_recipes, candidate_pool, variety_target
        pool = candidate_pool(ctx, eligible_recipes(ctx, RECIPES),
                              retry_budget=any('budget' in str(item).lower() for item in feedback))
        by_slot = {slot: [recipe['name'] for recipe in options] for slot, options in pool.items()}
        for meal in ctx.pinned:
            if meal['name'] not in by_slot[meal['slot']]:
                by_slot[meal['slot']].append(meal['name'])
        allowed = {name for names in by_slot.values() for name in names}
        offered={recipe['name']:recipe for options in pool.values() for recipe in options}
        from app.services.pricing import plan_checkout
        payload['approved_recipes'] = []
        for recipe in offered.values():
            row={key:value for key,value in recipe.items()
                 if key in {'name','slots','calories','protein','cost','cook_minutes'}}
            row['ingredients']=[item['name'] for item in recipe['ingredients']]
            # Useful basket context without transmitting complete recipe steps,
            # nutrient tables or every package offer on every paid request.
            row['shopping_cost_once']=plan_checkout([recipe],ctx.pantry,ctx.price_offers)[0]
            payload['approved_recipes'].append(row)
        payload['approved_names_by_slot'] = by_slot
        payload['planning_objectives'] = dict(variety_target=variety_target(ctx),
            preferred_checkout_range=[round(.75*ctx.budget,2),round(.95*ctx.budget,2)],
            hard_budget=ctx.budget, seed=ctx.seed,
            note='Use budget for varied, substantial meals and all selected nutrition goals. The range is a preference, not a minimum; pantry stock and partial weeks can make shopping cheaper.')
        required = [{'day': d.weekday, 'slot': slot} for d in ctx.active_days() for slot in ctx.slots_for(d.weekday)]
        payload['required_slots'] = required
        prompt = SYSTEM + "\nSelect ONLY names from approved_names_by_slot[slot]. Return {\"meals\":[{\"day\":0,\"slot\":\"breakfast\",\"name\":\"approved recipe name\"}]}. The server supplies trusted nutrition, ingredients and steps. Cover required_slots exactly. Prioritize every selected nutrition target, a variety of dishes and produce, preferences and workable prep. Use planning_objectives.variety_target as guidance; avoid repeating a dish more than three times unless the schedule, diet or a pin requires it. Use the available budget to improve variety and target fit; do not minimize spending or force needless spending. Whole-package shopping, after pantry deductions, must not exceed the hard budget; portion costs do not equal shopping totals. The preferred checkout range is a weak preference, not a required floor. On a budget retry reduce the package basket while preserving nutrition and variety. Use the supplied seed and changed shortlist to explore different recipes on regeneration."

        max_tokens = int(os.environ.get("LLM_MAX_OUTPUT_TOKENS", "5000"))
        pinned = {(m['day'], m['slot']) for m in ctx.pinned}

        def usable(raw):
            """Keep picks that are real recipes for their slot; a bad pick should cost one meal, not the plan."""
            good = []
            for m in (raw.get('meals') if isinstance(raw, dict) else None) or []:
                if not isinstance(m, dict):
                    continue
                if (m.get('day'), m.get('slot')) in pinned or m.get('name') in by_slot.get(m.get('slot'), ()):
                    good.append(m)
            return good

        meals = usable(self._ask(prompt, json.dumps(payload), max_tokens))
        for _ in range(2):  # small models drop or mis-slot a few picks; ask only for the gaps
            have = {(m.get('day'), m.get('slot')) for m in meals}
            missing = [x for x in required if (x['day'], x['slot']) not in have]
            if not missing:
                break
            extra = dict(payload, required_slots=missing, already_planned=[{'day': m.get('day'), 'slot': m.get('slot'), 'name': m.get('name')} for m in meals],
                         note="Return ONLY the missing meals, in the same JSON format.")
            try:
                meals += usable(self._ask(prompt, json.dumps(extra), max_tokens))
            except Exception:
                break
        wanted, seen, final = {(x['day'], x['slot']) for x in required}, set(), []
        for m in meals:  # one pick per required slot: drop duplicates and slots that aren't part of the plan
            key = (m.get('day'), m.get('slot'))
            if key in wanted and key not in seen:
                seen.add(key)
                final.append(m)
        from app.services.planning_quality import improve_plan
        return improve_plan(catalog_plan({'meals': final}, ctx), ctx, RECIPES)

    def interpret_preferences(self, text: str) -> Dict:
        if not (text or "").strip():
            return {"excluded": [], "day_minutes_cap": {}}
        system = (
            'Extract structured constraints from a student\'s free-text meal preferences. Return ONLY JSON: '
            '{"excluded": [ingredient or food-group words to never serve, e.g. "fish"], '
            '"day_minutes_cap": {"<weekday 0=Mon..6=Sun>": max cooking minutes that day}}. '
            'Use 15 for "hate cooking" and 0 for "no cooking". Weekday numbers: 0=Monday, 1=Tuesday, 2=Wednesday, '
            '3=Thursday, 4=Friday, 5=Saturday, 6=Sunday.'
        )
        try:
            out = self._ask(system, text, 500)
            from app.services.preference_text import interpret,merge_extractions
            return merge_extractions(interpret(text),normalize_preferences(out))
        except Exception:
            return FakeLLM().interpret_preferences(text)


class OpenAILLM(AnthropicLLM):
    """Same prompts and parsing as AnthropicLLM, served by the OpenAI chat API."""

    name = "openai"

    def __init__(self, api_key: str, model: str):
        import openai

        self.client = openai.OpenAI(api_key=api_key, timeout=float(os.environ.get("LLM_TIMEOUT_SECONDS", "60")), max_retries=0)
        self.metrics = []
        self.model = model

    def _ask(self, system: str, user: str, max_tokens: int):
        started = time.perf_counter()
        resp = self.client.chat.completions.create(
            model=self.model, max_tokens=max_tokens, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        usage = getattr(resp, "usage", None)
        if not hasattr(self, "metrics"):
            self.metrics = []
        self.metrics.append({"latency_seconds": round(time.perf_counter() - started, 3),
                             "input_tokens": getattr(usage, "prompt_tokens", None),
                             "output_tokens": getattr(usage, "completion_tokens", None),
                             "stop_reason": resp.choices[0].finish_reason})
        return _extract_json(resp.choices[0].message.content or "")


# ----------------------------------------------------------------------------- selection

def get_llm():
    """FastAPI dependency. Override in tests via app.dependency_overrides[get_llm]."""
    if settings.openai_api_key.strip():
        return OpenAILLM(settings.openai_api_key, settings.openai_model)
    if settings.anthropic_api_key.strip():
        return AnthropicLLM(settings.anthropic_api_key, settings.anthropic_model)
    return FakeLLM()
