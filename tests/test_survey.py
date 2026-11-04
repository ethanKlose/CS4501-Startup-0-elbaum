import pytest

from app.models import Profile
from tests.helpers import signup


def profile(client):
    with client.app.state.session_factory() as s:
        return s.query(Profile).first()


def test_survey_requires_login(client):
    assert client.get("/survey", follow_redirects=False).status_code == 303


def test_budget_saved(client):
    signup(client)
    r = client.post("/survey", data={"budget": "75.5"}, follow_redirects=False)
    assert r.status_code == 303
    assert profile(client).budget == 75.5
    assert "75.5" in client.get("/survey").text


@pytest.mark.parametrize("bad", ["", "0", "-5", "abc", "nan", "1e9"])
def test_budget_rejects_invalid(client, bad):
    signup(client)
    r = client.post("/survey", data={"budget": bad})
    assert r.status_code == 400
    assert "budget" in r.text.lower()
    p = profile(client)
    assert p is None or p.budget is None


def days_payload(**over):
    d = {}
    for i in range(7):
        d[f"minutes_{i}"] = "30"
    d.update(over)
    return d


def day_rows(client):
    from app.models import DaySetting

    with client.app.state.session_factory() as s:
        return {r.weekday: r for r in s.query(DaySetting).all()}


def test_days_saved_with_busy_flags(client):
    signup(client)
    payload = days_payload(minutes_0="10", busy_0="on", minutes_6="120")
    assert client.post("/survey", data=payload, follow_redirects=False).status_code == 303
    rows = day_rows(client)
    assert len(rows) == 7
    assert rows[0].busy and rows[0].minutes == 10
    assert not rows[6].busy and rows[6].minutes == 120


@pytest.mark.parametrize("bad", ["-1", "abc", "999", ""])
def test_days_reject_invalid_minutes(client, bad):
    signup(client)
    r = client.post("/survey", data=days_payload(minutes_2=bad))
    assert r.status_code == 400
    assert "Wednesday" in r.text
    assert not day_rows(client)


def test_budget_only_post_does_not_touch_days(client):
    signup(client)
    client.post("/survey", data=days_payload(minutes_0="5"))
    client.post("/survey", data={"budget": "50"})
    assert day_rows(client)[0].minutes == 5


def test_restrictions_saved_and_filtered(client):
    signup(client)
    client.post("/survey", data={"restrictions_present": "1", "restrictions": ["vegan", "nut_allergy", "bogus"]})
    assert profile(client).restrictions == ["nut_allergy", "vegan"]
    page = client.get("/survey").text
    assert 'value="vegan"\n      checked' in page or "checked> Vegan" in page


def test_restrictions_can_be_cleared(client):
    signup(client)
    client.post("/survey", data={"restrictions_present": "1", "restrictions": ["vegan"]})
    client.post("/survey", data={"restrictions_present": "1"})
    assert profile(client).restrictions == []


def test_other_posts_leave_restrictions_alone(client):
    signup(client)
    client.post("/survey", data={"restrictions_present": "1", "restrictions": ["vegan"]})
    client.post("/survey", data={"budget": "40"})
    assert profile(client).restrictions == ["vegan"]


def test_goal_high_protein(client):
    signup(client)
    client.post("/survey", data={"goal": "high_protein", "calorie_target": "1800"})
    p = profile(client)
    assert p.goal == "high_protein" and p.calorie_target is None


def test_goal_calorie_target(client):
    signup(client)
    client.post("/survey", data={"goal": "calorie_target", "calorie_target": "2200"})
    p = profile(client)
    assert p.goal == "calorie_target" and p.calorie_target == 2200


@pytest.mark.parametrize("cal", ["", "100", "99999", "abc"])
def test_calorie_target_validated(client, cal):
    signup(client)
    r = client.post("/survey", data={"goal": "calorie_target", "calorie_target": cal})
    assert r.status_code == 400 and "calorie" in r.text.lower()


def test_unknown_goal_rejected(client):
    signup(client)
    assert client.post("/survey", data={"goal": "bulk_up_fast"}).status_code == 400


def test_free_text_saved_and_trimmed(client):
    signup(client)
    client.post("/survey", data={"free_text": "  no fish, I hate cooking on Mondays  "})
    assert profile(client).free_text == "no fish, I hate cooking on Mondays"
    assert "no fish" in client.get("/survey").text


def test_free_text_too_long(client):
    signup(client)
    assert client.post("/survey", data={"free_text": "x" * 501}).status_code == 400


def pantry(client):
    from app.models import PantryItem

    with client.app.state.session_factory() as s:
        return s.query(PantryItem).all()


def test_pantry_add_remove(client):
    signup(client)
    client.post("/pantry/add", data={"name": " Rice ", "quantity": "2", "unit": "lb"})
    client.post("/pantry/add", data={"name": "salt"})
    items = pantry(client)
    assert {i.name for i in items} == {"rice", "salt"}
    assert "rice — 2 lb" in client.get("/survey").text
    rice = next(i for i in items if i.name == "rice")
    client.post(f"/pantry/{rice.id}/delete")
    assert {i.name for i in pantry(client)} == {"salt"}


def test_pantry_rejects_bad_input_and_dedupes(client):
    signup(client)
    client.post("/pantry/add", data={"name": ""})
    client.post("/pantry/add", data={"name": "rice", "quantity": "-3"})
    assert pantry(client) == []
    client.post("/pantry/add", data={"name": "rice", "quantity": "1"})
    client.post("/pantry/add", data={"name": "rice", "quantity": "5"})
    items = pantry(client)
    assert len(items) == 1 and items[0].quantity == 5


def test_cannot_delete_other_users_pantry_item(client):
    signup(client, "a@b.co")
    client.post("/pantry/add", data={"name": "rice"})
    item_id = pantry(client)[0].id
    client.post("/logout")
    signup(client, "c@d.co")
    client.post(f"/pantry/{item_id}/delete")
    assert len(pantry(client)) == 1


def test_new_user_is_sent_to_survey_then_home(client):
    signup(client)
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/survey"
    # Minimal completion: budget only; optional sections skipped.
    r = client.post("/survey", data={"budget": "60"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert client.get("/", follow_redirects=False).status_code == 200


def test_survey_without_budget_does_not_finish_setup(client):
    signup(client)
    client.post("/survey", data={"free_text": "hi"})
    assert client.get("/", follow_redirects=False).status_code == 303


def full_payload(**over):
    d = days_payload(busy_1="on")
    d.update({"budget": "80", "restrictions_present": "1", "restrictions": ["vegan"], "goal": "calorie_target",
              "calorie_target": "2000", "free_text": "no fish"})
    d.update(over)
    return d


def test_all_answers_viewable_and_editable_later(client):
    signup(client)
    client.post("/survey", data=full_payload())
    page = client.get("/survey").text
    assert 'value="80.0"' in page and "no fish" in page and 'value="2000"' in page
    assert "Your survey" in page  # no longer the first-run heading
    # edit every section
    client.post("/survey", data=days_payload(budget="45", restrictions_present="1", goal="high_protein",
                                             free_text="no nuts", minutes_3="90"))
    p = profile(client)
    assert (p.budget, p.restrictions, p.goal, p.free_text) == (45.0, [], "high_protein", "no nuts")
    assert day_rows(client)[3].minutes == 90 and not day_rows(client)[1].busy
