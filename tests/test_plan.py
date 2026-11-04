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
