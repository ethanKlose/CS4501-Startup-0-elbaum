"""Real Anthropic SDK -> HTTP transport -> catalog hydration -> retries -> saved plan.

Only HTTPTransport is substituted. No real key, billed request or model-quality
claim is involved; route dependencies, SDK parsing and app validators stay real.
"""
import json

import httpx
import anthropic
import pytest
from sqlalchemy import select

from app.models import Plan, Profile
from tests.integration.helpers import generate, onboard, pantry, post, shopping, snapshot

pytestmark = pytest.mark.integration

# The application's supported >=0.40 SDK range includes both HTTPX and HTTPX2
# generations. Patch the transport actually used by the installed real SDK.
if issubclass(anthropic.DefaultHttpxClient, httpx.Client):
    sdk_http = httpx
else:
    import httpx2 as sdk_http


def message(text):
    return sdk_http.Response(200, json={
        "id": "msg_integration", "type": "message", "role": "assistant", "model": "integration-model",
        "content": [{"type": "text", "text": text}], "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 120, "output_tokens": 80}})


def valid_choices(payload):
    # A controlled provider selects catalog names; the app must supply trusted details.
    names = {"breakfast": "Overnight oats with banana", "lunch": "Hummus veggie wrap", "dinner": "Hummus veggie wrap"}
    return {"meals": [dict(slot, name=names[slot["slot"]], calories=999999, cost=0, steps=["untrusted provider step"])
                      for slot in payload["required_slots"]]}


def attach_transport(monkeypatch, handler):
    def handle(transport, request):
        assert request.url.host == "api.anthropic.com"
        assert request.url.path == "/v1/messages"
        return handler(request)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "integration-dummy-key")
    monkeypatch.setenv("ANTHROPIC_MODEL", "integration-model")
    monkeypatch.setattr(sdk_http.HTTPTransport, "handle_request", handle)


def test_sdk_response_is_hydrated_validated_persisted_and_rendered(application, web, monkeypatch):
    onboard(web)
    calls = []
    def handler(request):
        body = json.loads(request.content)
        calls.append((request, body))
        payload = json.loads(body["messages"][0]["content"])
        return message(json.dumps(valid_choices(payload)))
    attach_transport(monkeypatch, handler)
    page = generate(web)
    saved = snapshot(application)
    assert len(calls) == 1
    headers = calls[0][0].headers
    assert (headers.get("x-api-key") == "integration-dummy-key"
            or headers.get("authorization") == "Bearer integration-dummy-key")
    assert calls[0][1]["model"] == "integration-model"
    assert saved["attempts"] == 1 and saved["settings"]["generation"]["engine"] == "anthropic"
    assert saved["settings"]["generation"]["api_calls"][0]["input_tokens"] == 120
    assert len(saved["meals"]) == 21 and saved["total_cost"] > 0
    assert all(m["calories"] < 999999 and "untrusted provider step" not in m["steps"] for m in saved["meals"])
    assert "untrusted provider step" not in page.text
    assert 'AI mode: plans use your configured model.' in page.text


def test_invalid_provider_output_is_fed_back_and_successful_retry_is_only_saved_plan(application, web, monkeypatch):
    onboard(web)
    payloads = []
    def handler(request):
        body = json.loads(request.content)
        payload = json.loads(body["messages"][0]["content"])
        payloads.append(payload)
        if len(payloads) == 1:
            return message('{"meals":[{"day":0,"slot":"breakfast","name":"Not an approved recipe"}]}')
        return message(json.dumps(valid_choices(payload)))
    attach_transport(monkeypatch, handler)
    generate(web)
    saved = snapshot(application)
    assert len(payloads) == saved["attempts"] == 2
    assert payloads[0]["feedback_from_previous_attempt"] == []
    assert payloads[1]["feedback_from_previous_attempt"]
    trace = saved["settings"]["generation"]["trace"]
    assert trace[0]["hard_errors"] and not trace[1]["hard_errors"]
    with application.sessions() as db:
        assert db.query(Plan).count() == 1


@pytest.mark.parametrize("failure", ["timeout", "http_503", "malformed_json", "wrong_shape", "missing_meals", "unknown_recipe"])
def test_exhausted_provider_failures_preserve_existing_plan_and_unsettled_inventory(application, web, monkeypatch, failure):
    onboard(web)
    generate(web)
    initial = snapshot(application)
    item = shopping(application, initial["id"])[0]
    assert post(web, "/grocery/toggle", {"key": item["key"], "checked": "true", "plan_id": initial["id"]}).status_code == 204
    before = snapshot(application)
    calls = []
    def handler(request):
        calls.append(request)
        if failure == "timeout":
            raise sdk_http.ReadTimeout("controlled integration timeout", request=request)
        if failure == "http_503":
            return sdk_http.Response(503, json={"type": "error", "error": {"type": "overloaded_error", "message": "controlled outage"}})
        text = {"malformed_json": "not JSON", "wrong_shape": '[]', "missing_meals": '{"meals":[]}',
                "unknown_recipe": '{"meals":[{"day":0,"slot":"breakfast","name":"Unknown dish"}]}'}[failure]
        return message(text)
    attach_transport(monkeypatch, handler)
    response = post(web, "/plan/regenerate")
    assert response.status_code == 303
    assert len(calls) == 3  # App attempts, no extra SDK retries.
    assert snapshot(application) == before
    assert pantry(application, before["user_id"]) == {}
    assert "alert" in web.get("/").text
    with application.sessions() as db:
        assert db.query(Plan).count() == 1


def test_failed_preference_extraction_falls_back_without_dropping_dietary_note(application, web, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        return message("not JSON")
    attach_transport(monkeypatch, handler)
    onboard(web, free_text="no fish, no red meat. No cooking on Wednesdays")
    with application.sessions() as db:
        profile = db.scalar(select(Profile))
        assert "fish" in profile.interpreted["excluded"]
        assert profile.interpreted["day_minutes_cap"] == {"2": 0}
    assert len(calls) == 1
    # Generate with the real offline adapter after extraction, through the normal route.
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    generate(web)
    saved = snapshot(application)
    assert "fish" in saved["settings"]["excluded"]
    assert all(m["cook_day"] != 2 for m in saved["meals"] if m["cook_minutes"])
