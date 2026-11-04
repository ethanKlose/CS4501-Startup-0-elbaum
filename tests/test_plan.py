import pytest

from app.models import Meal, Plan
from app.services.llm import FakeLLM, get_llm
from app.services.types import DayCtx, PlanContext
from tests.helpers import signup


def ctx(**kw):
    base = dict(budget=100.0, days=[DayCtx(i, 60) for i in range(7)])
    base.update(kw)
    return PlanContext(**base)


@pytest.fixture()
def onboarded(client):
    signup(client)
    client.post("/survey", data={"budget": "100"})
    return client


def plans(client):
    with client.app.state.session_factory() as s:
        return s.query(Plan).all()


def meals(client):
    with client.app.state.session_factory() as s:
        return s.query(Meal).all()


def test_generate_requires_login(client):
    assert client.post("/plan/generate", follow_redirects=False).headers["location"] == "/login"


def test_generate_full_week(onboarded):
    r = onboarded.post("/plan/generate", follow_redirects=False)
    assert r.status_code == 303
    ms = meals(onboarded)
    assert len(ms) == 21  # 7 days x 3 slots
    assert {(m.day, m.slot) for m in ms} == {(d, s) for d in range(7) for s in ("breakfast", "lunch", "dinner")}
    page = onboarded.get("/").text
    assert "Regenerate week" in page and ms[0].name in page


def test_fake_llm_is_valid_for_default_context():
    from app.services.validators import validate_plan

    c = ctx()
    plan, errors = validate_plan(FakeLLM().generate_plan(c), c)
    assert errors == [] and len(plan["meals"]) == 21


def test_malformed_llm_output_is_rejected(onboarded):
    class Bad:
        def interpret_preferences(self, t): return {"excluded": [], "day_minutes_cap": {}}
        def generate_plan(self, c, f=()): return {"meals": [{"day": 9}]}

    onboarded.app.dependency_overrides[get_llm] = lambda: Bad()
    r = onboarded.post("/plan/generate")  # follows redirect to "/", which shows the flash
    assert plans(onboarded) == []
    assert "valid plan" in r.text


def test_generate_needs_survey(client):
    signup(client)
    client.post("/plan/generate")
    assert plans(client) == []


class Scripted:
    """Fake LLM that replays canned plans and records the feedback it receives."""

    def __init__(self, *plans):
        self.plans, self.calls = list(plans), []

    def interpret_preferences(self, t):
        return {"excluded": [], "day_minutes_cap": {}}

    def generate_plan(self, c, feedback=()):
        self.calls.append(list(feedback))
        return self.plans.pop(0) if len(self.plans) > 1 else self.plans[0]


def good_plan(**kw):
    return FakeLLM().generate_plan(ctx(**kw))


def scale_costs(plan, factor):
    import copy

    p = copy.deepcopy(plan)
    for m in p["meals"]:
        for i in m["ingredients"]:
            i["cost"] = round(i["cost"] * factor, 2)
        m["cost"] = round(sum(i["cost"] for i in m["ingredients"]), 2)
    return p


def test_over_budget_plan_is_never_saved_and_retried(onboarded):
    good = good_plan()
    llm = Scripted(scale_costs(good, 10), good)  # first attempt blows the budget
    onboarded.app.dependency_overrides[get_llm] = lambda: llm
    onboarded.post("/plan/generate")
    assert len(llm.calls) == 2
    assert llm.calls[0] == [] and "exceeds the weekly budget" in llm.calls[1][0]  # error fed back
    ps = plans(onboarded)
    assert len(ps) == 1 and ps[0].attempts == 2 and ps[0].total_cost <= 100


def test_gives_up_after_max_attempts(onboarded):
    llm = Scripted(scale_costs(good_plan(), 10))
    onboarded.app.dependency_overrides[get_llm] = lambda: llm
    r = onboarded.post("/plan/generate")
    assert len(llm.calls) == 3
    assert plans(onboarded) == []
    assert "exceeds the weekly budget" in r.text


def test_budget_is_a_hard_limit_for_real_fake_llm(client):
    signup(client)
    client.post("/survey", data={"budget": "30"})
    client.post("/plan/generate")
    for p in plans(client):
        assert p.total_cost <= 30
