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
