def test_live_evaluation_is_honestly_unavailable_without_key(monkeypatch):
    from scripts.evaluate_planner import evaluate
    monkeypatch.setenv('ANTHROPIC_API_KEY','')
    report=evaluate(live=True)
    assert report['status']=='unavailable' and report['results']==[]
