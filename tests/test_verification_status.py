from sqlalchemy import select
from app.models import Plan
from tests.helpers import signup


def generate(client,**values):
    signup(client);client.post('/survey',data=dict(budget='150',**values))
    return client.post('/plan/generate',data={'start_mode':'next_week'}).text


def test_goal_shortfall_is_never_called_verified(client):
    html=generate(client,goal='calorie_target',calorie_target='4500')
    assert 'Needs review' in html and 'Verified plan' not in html
    assert 'Nutrition goal:</strong> Needs review' in html


def test_unparsed_notes_remain_visible_after_edits(client):
    html=generate(client,free_text='Only locally sourced seasonal ingredients')
    assert 'Extra notes:</strong> Needs review' in html
    client.post('/plan/days/2/skip')
    assert 'Extra notes:</strong> Needs review' in client.get('/').text


def test_legacy_plan_is_unverified_when_rule_snapshot_is_missing(client):
    generate(client)
    with client.app.state.session_factory() as db:
        p=db.scalar(select(Plan));st=dict(p.settings);st.pop('restrictions');p.settings=st;db.commit()
    html=client.get('/').text
    assert 'Diet and kitchen rules:</strong> Not recorded' in html and 'Needs review' in html


def test_clean_plan_shows_individual_scoped_checks(client):
    html=generate(client)
    assert 'Checks passed' in html and 'Budget estimate:</strong> Passed' in html
    assert 'Nutrition goal:</strong> Not requested' in html
