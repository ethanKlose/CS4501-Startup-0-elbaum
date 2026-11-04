import pytest

from app.models import Meal, Plan
from tests.helpers import signup


@pytest.fixture()
def planned(client):
    signup(client)
    client.post("/survey", data={"budget": "100"})
    client.post("/plan/generate")
    return client


def meals(client):
    with client.app.state.session_factory() as s:
        return s.query(Meal).order_by(Meal.id).all()


def test_mark_cooked_and_skipped_persist_and_show_on_calendar(planned):
    ms = meals(planned)
    planned.post(f"/meals/{ms[0].id}/status", data={"status": "cooked"})
    planned.post(f"/meals/{ms[1].id}/status", data={"status": "skipped"})
    after = meals(planned)
    assert (after[0].status, after[1].status, after[2].status) == ("cooked", "skipped", "planned")
    page = planned.get("/").text
    assert 'data-status="cooked"' in page and 'data-status="skipped"' in page
    assert "Mark cooked" in planned.get(f"/meals/{ms[2].id}").text


def test_status_can_be_reset(planned):
    m = meals(planned)[0]
    planned.post(f"/meals/{m.id}/status", data={"status": "cooked"})
    planned.post(f"/meals/{m.id}/status", data={"status": "planned"})
    assert meals(planned)[0].status == "planned"


def test_invalid_status_and_other_users(planned):
    m = meals(planned)[0]
    assert planned.post(f"/meals/{m.id}/status", data={"status": "eaten"}).status_code == 422
    planned.post("/logout")
    signup(planned, "o@o.co")
    assert planned.post(f"/meals/{m.id}/status", data={"status": "cooked"}).status_code == 404
