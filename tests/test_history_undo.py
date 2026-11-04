from app.models import PantryItem, Plan
from tests.helpers import signup


def test_history_is_private_and_checkin_can_be_undone(client):
    signup(client);client.post('/survey',data={'budget':'150'});client.post('/plan/generate')
    with client.app.state.session_factory() as s:p=s.query(Plan).first();pid=p.id
    client.post('/checkin',data={'bought_all':'true'})
    with client.app.state.session_factory() as s:assert s.query(PantryItem).count()>0
    assert client.post('/checkin/undo',data={'plan_id':pid}).status_code==200
    with client.app.state.session_factory() as s:
        assert all(p.quantity==0 for p in s.query(PantryItem))
        assert not s.get(Plan,pid).settings['inventory']['settled']
    client.post('/plan/next-week')
    assert f'/plans/{pid}' in client.get('/plans').text
    assert 'Archived plan' in client.get(f'/plans/{pid}').text
    assert client.post('/checkin/undo',data={'plan_id':pid}).status_code==409
    client.post('/logout');signup(client,'other-history@example.test')
    client.post('/survey',data={'budget':'150'})
    assert client.get(f'/plans/{pid}').status_code==404
