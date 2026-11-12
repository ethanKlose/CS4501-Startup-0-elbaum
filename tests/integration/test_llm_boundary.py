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
    return {"meals": [dict(slot, name=(names[slot["slot"]] if names[slot["slot"]] in payload["approved_names_by_slot"][slot["slot"]] else payload["approved_names_by_slot"][slot["slot"]][0]), calories=999999, cost=0, steps=["untrusted provider step"])
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


def test_invalid_pick_is_repaired_for_only_missing_slot_and_saved_once(application, web, monkeypatch):
    onboard(web)
    payloads = []
    def handler(request):
        body = json.loads(request.content)
        payload = json.loads(body["messages"][0]["content"])
        payloads.append(payload)
        if len(payloads) == 1:
            choices = valid_choices(payload)
            choices["meals"][-1]["name"] = "Not an approved recipe"
            return message(json.dumps(choices))
        return message(json.dumps(valid_choices(payload)))
    attach_transport(monkeypatch, handler)
    generate(web)
    saved = snapshot(application)
    assert len(payloads) == 2 and saved["attempts"] == 1
    assert payloads[0]["feedback_from_previous_attempt"] == []
    assert payloads[1]["required_slots"] == [payloads[0]["required_slots"][-1]]
    assert len(payloads[1]["already_planned"]) == 20
    assert payloads[1]["note"] == "Return ONLY the missing meals, in the same JSON format."
    trace = saved["settings"]["generation"]["trace"]
    assert len(trace) == 1 and not trace[0]["hard_errors"]
    assert len(saved["settings"]["generation"]["api_calls"]) == 2
    assert len(saved["meals"]) == 21
    with application.sessions() as db:
        assert db.query(Plan).count() == 1


def test_diet_incompatible_recipe_is_not_offered_and_is_repaired_before_save(application, web, monkeypatch):
    onboard(web, restrictions_present="1", restrictions=["vegan"])
    payloads = []
    def handler(request):
        body = json.loads(request.content)
        payload = json.loads(body["messages"][0]["content"])
        payloads.append(payload)
        choices = valid_choices(payload)
        if len(payloads) == 1:
            for meal in choices["meals"]:
                if meal["slot"] == "breakfast":
                    meal["name"] = "Overnight oats with banana"  # milk: not offered for vegan
        return message(json.dumps(choices))
    attach_transport(monkeypatch, handler)
    generate(web)
    saved = snapshot(application)
    assert "Overnight oats with banana" not in payloads[0]["approved_names_by_slot"]["breakfast"]
    assert len(payloads) == 2 and saved["attempts"] == 1
    assert len(payloads[0]["required_slots"]) == 21
    assert len(payloads[1]["required_slots"]) == 7
    assert all(slot["slot"] == "breakfast" for slot in payloads[1]["required_slots"])
    assert "already_planned" in payloads[1]
    assert not saved["settings"]["generation"]["trace"][0]["hard_errors"]
    assert all(meal["name"] != "Overnight oats with banana" for meal in saved["meals"])
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
    # Semantically incomplete responses allow two gap-fill requests inside each
    # of three planner attempts. Transport/JSON failures stop that inner pass.
    expected_calls = 9 if failure in {"missing_meals", "unknown_recipe"} else 3
    assert len(calls) == expected_calls
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
