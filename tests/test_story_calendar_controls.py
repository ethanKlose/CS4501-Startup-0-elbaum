"""Stories #17-#21: schedule input boundaries and immutable closed history."""
import pytest
from tests.helpers import signup
from app.models import Meal
from app.routers.lifestyle import parse_clock

@pytest.mark.parametrize('raw',['7:00','07:0','24:00','12:60','07:00junk',''])
def test_clocks_require_valid_hhmm(raw):
    with pytest.raises(ValueError):parse_clock(raw)


def test_valid_clock_boundaries():
    assert parse_clock('00:00')==0
    assert parse_clock('23:59')==1439


def test_closed_plan_pins_cannot_change(client):
    signup(client);client.post('/survey',data={'budget':'150'});client.post('/plan/generate')
    with client.app.state.session_factory() as db:m=db.query(Meal).first();mid=m.id;pin=m.pinned
    client.post('/checkin')
    assert client.post(f'/meals/{mid}/pin').status_code==409
    with client.app.state.session_factory() as db:assert db.get(Meal,mid).pinned==pin


def test_window_count_limit(client):
    signup(client)
    assert client.post('/preferences/schedule',data={'windows_0':','.join(['00:00-00:01']*9)}).status_code==400
