"""Actual OpenAI responses drive the app; model failures remain test failures."""
from collections import Counter

import pytest
from sqlalchemy import select
from live_tests.cost_guard import RATES

pytestmark = pytest.mark.live


def post(web, path, data=None):
    if not web.cookies.get("csrf_token"):
        assert web.get("/health").status_code == 200
    return web.post(path, data={"csrf_token": web.cookies["csrf_token"], **(data or {})})


def require_provider_success(budget):
    statuses = [call["http_status"] for call in budget.calls]
    if any(status in (401, 403) for status in statuses):
        pytest.fail("OpenAI authentication/access failed; check the local OpenAI key and project", pytrace=False)
    if any(status == 429 for status in statuses):
        pytest.fail("OpenAI returned 429; check API balance, project limits and rate limits", pytrace=False)
    if budget.stop_reason:
        pytest.fail(budget.stop_reason + "; this is a paid-test limit, not proof that a plan is impossible", pytrace=False)
    assert statuses and all(status == 200 for status in statuses), f"Provider HTTP statuses: {statuses}"
    assert all(call.get("response_model") in RATES for call in budget.calls), "Provider returned an unpriced model version"
    assert all(call["input_tokens"] is not None and call["output_tokens"] is not None for call in budget.calls)


def test_live_credentials_and_json(real_app):
    from app.services.llm import get_llm
    llm = get_llm()
    assert llm.name == "openai"
    try:
        try:
            reply = llm._ask("Return a JSON object only.", 'Return {"status":"ok"}.', 32)
        except Exception:
            require_provider_success(real_app.budget)
            pytest.fail("Live API call did not return the required JSON; inspect the usage/status report", pytrace=False)
        assert reply == {"status": "ok"}
        require_provider_success(real_app.budget)
        assert len(real_app.budget.calls) == 1
    finally:
        llm.client.close()


def create_real_plan(real_app, restrictions=()):
    from app.models import Plan
    web = real_app.web
    assert post(web, "/register", {"email": "live-test@example.test", "password": "LiveTestOnly123!"}).status_code == 303
    # Blank free text avoids a separate paid preference-interpretation request.
    data = {"budget": "200", "goal": "none", "free_text": "", "restrictions_present": "1", "restrictions": list(restrictions)}
    data.update({f"minutes_{day}": "60" for day in range(7)})
    assert post(web, "/survey", data).status_code == 303
    before = len(real_app.budget.calls)
    assert post(web, "/plan/generate").status_code == 303
    require_provider_success(real_app.budget)
    assert len(real_app.budget.calls) > before, "No real provider request was observed"
    with real_app.sessions() as db:
        plans = list(db.scalars(select(Plan)))
        assert len(plans) == 1, "Live output did not produce one accepted plan within the test limits"
        plan = plans[0]
        assert plan.settings["generation"]["engine"] == "openai"
        assert len(plan.meals) == 21
        assert Counter((m.day, m.slot) for m in plan.meals) == Counter(
            (d, slot) for d in range(7) for slot in ("breakfast", "lunch", "dinner"))
        assert plan.settings["checkout_total"] <= 200
        from app.services.validators import validate_full
        from app.services.planner import plan_ctx
        _, hard, soft = validate_full({"meals": [m.as_dict() for m in plan.meals]}, plan_ctx(plan))
        assert not hard, f"Encoded hard constraints failed: {hard}"
        assert not soft, f"This simple live scenario still needs review: {soft}"
        return plan.id, plan.meals[0].id


def test_live_weekly_workflow(real_app):
    from app.models import CheckIn, Meal
    pid, mid = create_real_plan(real_app)
    web = real_app.web
    used = len(real_app.budget.calls)
    assert 'id="meals-data"' in web.get("/").text
    assert "Ingredients" in web.get(f"/meals/{mid}").text
    assert 'class="plain grocery"' in web.get("/grocery").text
    calendar = web.get(f"/plans/{pid}/calendar.ics")
    assert calendar.status_code == 200 and calendar.text.count("BEGIN:VEVENT") >= 21
    assert post(web, f"/meals/{mid}/pin").status_code == 303
    assert post(web, f"/meals/{mid}/status", {"status": "cooked"}).status_code == 303
    assert post(web, f"/meals/{mid}/rate", {"rating": "5"}).status_code == 303
    assert post(web, "/checkin", {"plan_id": pid}).status_code == 303
    with real_app.sessions() as db:
        assert db.get(Meal, mid).rating == 5
        assert db.get(Meal, mid).pinned
        assert db.scalar(select(CheckIn)).plan_id == pid
    assert len(real_app.budget.calls) == used, "Viewing/checking off a saved plan should not make paid requests"


def test_live_vegetarian_plan(real_app):
    from app.models import Plan
    pid, _ = create_real_plan(real_app, restrictions=("vegetarian",))
    with real_app.sessions() as db:
        plan = db.get(Plan, pid)
        assert plan.settings["restrictions"] == ["vegetarian"]
        forbidden = ("chicken", "turkey", "beef", "pork", "tuna", "salmon", "shrimp")
        assert not any(word in ingredient["name"].lower() for meal in plan.meals
                       for ingredient in meal.ingredients for word in forbidden)
