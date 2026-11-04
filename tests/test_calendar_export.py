from tests.helpers import signup
from app.models import Plan


def test_export_is_private_and_has_valid_calendar_boundaries(client):
    signup(client);client.post('/survey',data={'budget':'150'});client.post('/plan/generate')
    with client.app.state.session_factory() as s:pid=s.query(Plan).first().id
    response=client.get(f'/plans/{pid}/calendar.ics')
    assert response.status_code==200 and response.text.startswith('BEGIN:VCALENDAR\r\n')
    assert response.text.count('BEGIN:VEVENT')>=21
    assert 'DTSTART;TZID=America/New_York:' in response.text
    assert all(len(line.encode('utf-8'))<=75 for line in response.text.split('\r\n'))
    client.post('/logout');signup(client,'calendar-other@example.test');client.post('/survey',data={'budget':'150'})
    assert client.get(f'/plans/{pid}/calendar.ics').status_code==404
