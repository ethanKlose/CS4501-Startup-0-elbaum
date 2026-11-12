"""The real client can't be called without a key, so test it against a stub of the SDK object."""
import json
from types import SimpleNamespace

from app.services.llm import SYSTEM, AnthropicLLM, FakeLLM, _extract_json
from app.services.types import DayCtx, PlanContext
from app.services.validators import validate_full


class StubClient:
    def __init__(self, text):
        self.text, self.calls = text, []
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.text)])


def client_with(text):
    llm = AnthropicLLM.__new__(AnthropicLLM)  # skip __init__: no SDK/key needed
    llm.client, llm.model = StubClient(text), "test-model"
    return llm


def ctx():
    return PlanContext(budget=150, days=[DayCtx(i, 0 if i in (2, 3) else 60) for i in range(7)], prep_days=[6], prep_minutes=150)


def offered_plan(context):
    """The provider can only choose recipes actually present in its payload."""
    from unittest.mock import patch
    from app.services.catalog import RECIPES
    from app.services.planning_quality import candidate_pool, eligible_recipes
    pools = candidate_pool(context, eligible_recipes(context, RECIPES))
    recipes = {}
    for slot,options in pools.items():
        for recipe in options:
            if recipe['name'] not in recipes:
                recipes[recipe['name']] = dict(recipe, slots=[])
            recipes[recipe['name']]['slots'].append(slot)
    with patch('app.services.llm.RECIPES', list(recipes.values())):
        return FakeLLM()._generate(context)


def test_extract_json_handles_fences_and_chatter():
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _extract_json('Sure! Here you go: {"a": {"b": 2}} Enjoy.') == {"a": {"b": 2}}


def test_generate_plan_sends_capacity_and_feedback_and_parses():
    c = ctx()
    plan = offered_plan(c)
    llm = client_with("```json\n" + json.dumps(plan) + "\n```")
    out = llm.generate_plan(c, ["Missing lunch on Monday."])
    sent = llm.client.calls[0]
    payload = json.loads(sent["messages"][0]["content"])
    assert payload["cook_capacity_minutes"]["2"] == 0 and payload["cook_capacity_minutes"]["-1"] == 150
    assert payload["feedback_from_previous_attempt"] == ["Missing lunch on Monday."]
    assert sent["system"].startswith(SYSTEM) and sent["model"] == "test-model"
    _, hard, soft = validate_full(out, c)
    assert hard == []


def test_prompt_tells_model_busy_days_still_get_meals():
    assert "busy" in SYSTEM and "does NOT mean fewer meals" in SYSTEM and "scheduler" in SYSTEM


def test_garbage_from_the_model_is_a_failed_attempt_not_a_crash():
    from app.services.planner import run_with_retries, PlanFailed
    import pytest

    llm = client_with("I am sorry, I cannot do that.")
    with pytest.raises(PlanFailed):
        run_with_retries(llm, ctx())
    assert len(llm.client.calls) == 3  # retried, fed back, then gave up


def test_interpret_preferences_falls_back_if_model_fails():
    llm = client_with("not json at all")
    out = llm.interpret_preferences("no fish, I can't cook on Wednesdays")
    assert out["excluded"] == ["fish"] and out["day_minutes_cap"] == {"2": 0}


def test_invalid_preference_days_fall_back_instead_of_crashing_survey():
    llm=client_with('{"excluded":[],"day_minutes_cap":{"7":15}}')
    out=llm.interpret_preferences('No cooking on Wednesdays')
    assert out['day_minutes_cap']=={'2':0}


def test_bad_picks_are_dropped_and_gaps_are_filled_instead_of_failing_the_plan():
    from app.services.catalog import RECIPES

    c = ctx()
    good = offered_plan(c)["meals"]
    picks = [{"day": m["day"], "slot": m["slot"], "name": m["name"]} for m in good]
    broken = [dict(picks[0], name="Not a real recipe")] + picks[1:5]  # one invented name, the rest of the plan missing
    replies = [json.dumps({"meals": broken}), json.dumps({"meals": picks})]
    llm = AnthropicLLM.__new__(AnthropicLLM)
    llm.model = "test-model"
    llm._ask = lambda system, user, max_tokens: json.loads(replies.pop(0))
    plan = llm.generate_plan(c)
    got = {(m["day"], m["slot"]) for m in plan["meals"]}
    assert got == {(p["day"], p["slot"]) for p in picks}  # every slot filled, invented recipe never kept
    assert all(m["name"] in {r["name"] for r in RECIPES} for m in plan["meals"])
