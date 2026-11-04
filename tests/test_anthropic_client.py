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


def test_extract_json_handles_fences_and_chatter():
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _extract_json('Sure! Here you go: {"a": {"b": 2}} Enjoy.') == {"a": {"b": 2}}


def test_generate_plan_sends_capacity_and_feedback_and_parses():
    c = ctx()
    plan = FakeLLM().generate_plan(c)
    llm = client_with("```json\n" + json.dumps(plan) + "\n```")
    out = llm.generate_plan(c, ["Missing lunch on Monday."])
    sent = llm.client.calls[0]
    payload = json.loads(sent["messages"][0]["content"])
    assert payload["cook_capacity_minutes"]["2"] == 0 and payload["cook_capacity_minutes"]["-1"] == 150
    assert payload["feedback_from_previous_attempt"] == ["Missing lunch on Monday."]
    assert sent["system"] == SYSTEM and sent["model"] == "test-model"
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
