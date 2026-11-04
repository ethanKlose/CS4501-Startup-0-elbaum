def test_missing_or_incorrect_csrf_cannot_create_account(client):
    assert client.post('/register',data={'email':'csrf@example.test','password':'password123'},headers={'X-CSRF-Token':''}).status_code==403
    assert client.post('/register',data={'email':'csrf@example.test','password':'password123'},headers={'X-CSRF-Token':'wrong'}).status_code==403
    assert client.post('/register',data={'email':'csrf@example.test','password':'password123'},follow_redirects=False).status_code==303


def test_forms_and_ajax_receive_session_token(client):
    response=client.get('/register')
    assert 'name="csrf_token"' in response.text
    assert client.cookies.get('csrf_token') in response.text
