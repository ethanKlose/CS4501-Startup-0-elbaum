from tests.helpers import signup
from scripts.export_study import export


def test_only_consented_numeric_feedback_is_exported(client):
    signup(client)
    values=dict(actual_spend=50,actual_minutes=10,baseline_minutes=25,ease=4,notes='private free text')
    client.post('/feedback',data=values)
    client.post('/feedback',data=dict(values,consent='true'))
    with client.app.state.session_factory() as db:report=export(db)
    assert len(report['results'])==1
    assert 'private free text' not in str(report) and 'notes' not in str(report)
