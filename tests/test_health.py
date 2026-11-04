def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_planner_mode_is_visible_and_honest(client, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', '')
    assert 'Demo mode: plans use a built-in recipe catalog' in client.get('/').text
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'configured-but-not-tested')
    assert 'AI mode: plans use your configured model.' in client.get('/').text
    assert 'Live AI is not connected' not in client.get('/').text
