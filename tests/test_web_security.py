def test_missing_or_incorrect_csrf_cannot_create_account(client):
    assert client.post('/register',data={'email':'csrf@example.test','password':'password123'},headers={'X-CSRF-Token':''}).status_code==403
    assert client.post('/register',data={'email':'csrf@example.test','password':'password123'},headers={'X-CSRF-Token':'wrong'}).status_code==403
    assert client.post('/register',data={'email':'csrf@example.test','password':'password123'},follow_redirects=False).status_code==303


def test_forms_and_ajax_receive_session_token(client):
    response=client.get('/register')
    assert 'name="csrf_token"' in response.text
    assert client.cookies.get('csrf_token') in response.text


def test_shared_rate_counter_blocks_and_expires(session_factory):
    from app.rate_limits import hit
    with session_factory() as db:
        assert hit(db,'login','same-ip',2,60,now=1)
    with session_factory() as db:
        assert hit(db,'login','same-ip',2,60,now=2)
        assert not hit(db,'login','same-ip',2,60,now=3)
        assert hit(db,'login','same-ip',2,60,now=61)


def test_production_rejects_default_secrets(monkeypatch):
    import pytest
    from app.config import settings
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.setenv('SECRET_KEY','change-me-in-prod')
    with pytest.raises(RuntimeError,match='SECRET_KEY'):settings.validate()
