"""Free unit checks for paid-test spending controls; these never contact a provider."""
from decimal import Decimal

import httpx
import pytest

from live_tests.cost_guard import CallBudget, LiveBudgetExceeded


def request(**changes):
    body = {"model": "gpt-4o-mini", "max_tokens": 32, "messages": [{"role": "user", "content": "Return JSON."}]}
    body.update(changes)
    return httpx.Request("POST", "https://api.openai.com/v1/chat/completions", json=body)


def test_guard_forwards_response_unchanged_and_records_usage_without_headers():
    budget = CallBudget("gpt-4o-mini")
    sent = []
    response = httpx.Response(200, json={"model": "gpt-4o-mini-2024-07-18", "usage": {"prompt_tokens": 10, "completion_tokens": 5}, "choices": [{"message": {"content": "actual upstream content"}}]})
    def upstream(transport, outgoing):
        sent.append(outgoing)
        return response
    handler = budget.forwarding_handler(upstream)
    outgoing = request()
    outgoing.headers["Authorization"] = "Bearer guard-unit-secret"
    assert handler(None, outgoing) is response
    assert sent == [outgoing]
    report = budget.report()
    assert report["paid_attempts"] == 1 and report["calls"][0]["http_status"] == 200
    assert report["calls"][0]["response_model"] == "gpt-4o-mini-2024-07-18"
    assert report["estimated_usage_usd"] == pytest.approx(0.0000045)
    assert "guard-unit-secret" not in str(report) and "upstream content" not in str(report)


def test_call_limit_blocks_before_a_second_provider_attempt():
    budget = CallBudget("gpt-4o-mini", max_calls=1)
    sent = []
    def upstream(transport, outgoing):
        sent.append(outgoing)
        return httpx.Response(200, json={})
    handler = budget.forwarding_handler(upstream)
    handler(None, request())
    with pytest.raises(LiveBudgetExceeded, match="request-count"):
        handler(None, request())
    assert len(sent) == len(budget.calls) == 1


def test_dollar_reservation_blocks_before_any_provider_attempt():
    budget = CallBudget("gpt-4o-mini", budget_usd=Decimal("0.000001"))
    def forbidden(transport, outgoing):
        pytest.fail("Budget rejection must happen before network transport")
    with pytest.raises(LiveBudgetExceeded, match="dollar budget"):
        budget.forwarding_handler(forbidden)(None, request())
    assert budget.calls == [] and budget.reserved_usd == 0


def test_timed_out_request_keeps_its_reservation_and_cannot_retry():
    budget = CallBudget("gpt-4o-mini", max_calls=1)
    def timeout(transport, outgoing):
        raise httpx.ReadTimeout("controlled timeout")
    handler = budget.forwarding_handler(timeout)
    with pytest.raises(httpx.ReadTimeout):
        handler(None, request())
    assert budget.reserved_usd > 0 and budget.calls[0]["transport_error"]
    assert budget.report()["estimated_usage_usd"] is None
    with pytest.raises(LiveBudgetExceeded):
        handler(None, request())


@pytest.mark.parametrize("url", ["http://api.openai.com/v1/chat/completions", "https://other.example/v1/chat/completions", "https://api.openai.com/v1/models"])
def test_guard_rejects_other_endpoints(url):
    outgoing = request()
    outgoing.url = httpx.URL(url)
    with pytest.raises(LiveBudgetExceeded, match="endpoint"):
        CallBudget("gpt-4o-mini").reserve(outgoing)


@pytest.mark.parametrize("limit", [None, 0, 2001, True])
def test_guard_requires_explicit_bounded_output(limit):
    with pytest.raises(LiveBudgetExceeded, match="max_tokens"):
        CallBudget("gpt-4o-mini").reserve(request(max_tokens=limit))


@pytest.mark.parametrize("changes", [{"stream": True}, {"n": 2}, {"tools": [{"type": "function"}]}, {"modalities": ["audio"]}, {"service_tier": "priority"}, {"model": "expensive-model"}])
def test_unpriced_or_multiple_completion_features_are_rejected(changes):
    with pytest.raises(LiveBudgetExceeded):
        CallBudget("gpt-4o-mini").reserve(request(**changes))


@pytest.mark.parametrize("settings", [{"max_calls": 0}, {"max_calls": 4}, {"max_calls": 1.5}, {"budget_usd": "NaN"}, {"budget_usd": "0.11"}, {"output_limit": 2001}])
def test_invalid_spending_configuration_is_rejected(settings):
    with pytest.raises(ValueError):
        CallBudget("gpt-4o-mini", **settings)


def test_http_error_is_recorded_without_storing_provider_error_text():
    budget = CallBudget("gpt-4o-mini")
    handler = budget.forwarding_handler(lambda transport, outgoing: httpx.Response(401, json={"error": {"message": "private-provider-error"}}))
    handler(None, request())
    report = budget.report()
    assert report["calls"][0]["http_status"] == 401
    assert report["estimated_usage_usd"] is None
    assert "private-provider-error" not in str(report)
