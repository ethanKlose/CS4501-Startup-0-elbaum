from sqlalchemy import select
from app.models import Plan,UserPreference
from scripts.export_study import export
from tests.helpers import signup

VALUES=dict(actual_spend=40,actual_minutes=10,baseline_minutes=25,ease=4)


def test_correctness_review_records_original_plan_and_excludes_private_notes(client):
    signup(client);client.post('/survey',data={'budget':'150'});client.post('/plan/generate')
    with client.app.state.session_factory() as db:pid=db.scalar(select(Plan.id))
    client.post('/plan/regenerate')
    r=client.post('/feedback',data=dict(VALUES,plan_id=pid,plan_correct='no',failed_constraints=['diet','budget'],consent='true',notes='private review notes'))
    assert r.status_code==200
    with client.app.state.session_factory() as db:
        entry=db.scalar(select(UserPreference)).data['study_entries'][0]
        assert entry['plan_id']==pid and entry['automatic_checks']
        result=export(db)['results'][0]
        assert result['plan_correct']=='no' and result['failed_constraints']==['budget','diet']
        assert result['correctness_source']=='student self-review'
        assert 'private review notes' not in str(result) and 'plan_id' not in result


def test_unreviewed_and_inconsistent_results_are_distinguished(client):
    signup(client)
    assert client.post('/feedback',data=dict(VALUES,plan_correct='yes')).status_code==400
    client.post('/survey',data={'budget':'150'});client.post('/plan/generate')
    assert client.post('/feedback',data=dict(VALUES,plan_correct='yes',failed_constraints=['diet'])).status_code==400
    assert client.post('/feedback',data=dict(VALUES,plan_correct='no',failed_constraints=['private arbitrary text'])).status_code==400
    assert client.post('/feedback',data=dict(VALUES,consent='true')).status_code==200
    with client.app.state.session_factory() as db:assert export(db)['results'][0]['plan_correct']=='not_reviewed'


def test_other_accounts_plan_cannot_be_reviewed(client):
    signup(client);client.post('/survey',data={'budget':'150'});client.post('/plan/generate')
    with client.app.state.session_factory() as db:pid=db.scalar(select(Plan.id))
    client.post('/logout');signup(client,email='other-review@example.test')
    assert client.post('/feedback',data=dict(VALUES,plan_id=pid,plan_correct='yes')).status_code==404


def test_correctness_summary_counts_accounts_once_and_keeps_missing_results_unknown(client):
    from scripts.export_study import correctness_summary
    signup(client);client.post('/survey',data={'budget':'150'});client.post('/plan/generate')
    client.post('/feedback',data=dict(VALUES,plan_correct='yes',consent='true'))
    client.post('/feedback',data=dict(VALUES,plan_correct='no',consent='true'))
    with client.app.state.session_factory() as db:
        summary=correctness_summary(db)
        assert summary['reviewed_accounts']==1 and summary['correct_accounts']==0
        assert summary['meets_threshold'] is None and summary['status']=='incomplete'


def test_correctness_can_be_reviewed_without_collecting_times_or_spending(client):
    signup(client);client.post('/survey',data={'budget':'150'});client.post('/plan/generate')
    response=client.post('/feedback',data={'plan_correct':'yes','consent':'true','actual_spend':'','actual_minutes':'','baseline_minutes':'','ease':''})
    assert response.status_code==200
    with client.app.state.session_factory() as db:
        result=export(db)['results'][0]
        assert result['plan_correct']=='yes' and result['actual_minutes'] is None and result['baseline_minutes'] is None
