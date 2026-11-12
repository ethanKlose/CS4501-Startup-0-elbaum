"""HTTP form -> owned grocery ledger -> real adapter -> controlled provider transport."""
import json

import httpx
import pytest

from tests.integration.helpers import generate, onboard, post, shopping, snapshot

pytestmark = pytest.mark.integration


def attach_transport(monkeypatch, handler):
    monkeypatch.setenv("INSTACART_API_KEY", "integration-shopping-key")
    monkeypatch.setenv("INSTACART_ENV", "development")
    def handle(transport, request):
        assert str(request.url) == "https://connect.dev.instacart.tools/idp/v1/products/products_link"
        assert request.headers["Authorization"] == "Bearer integration-shopping-key"
        return handler(request)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle)


def test_unchecked_list_is_serialized_and_cache_is_invalidated_when_list_changes(application, web, monkeypatch):
    onboard(web)
    generate(web)
    saved = snapshot(application)
    items = shopping(application, saved["id"])
    first = items[0]
    assert post(web, "/grocery/toggle", {"key": first["key"], "checked": "true", "plan_id": saved["id"]}).status_code == 204
    bodies = []
    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"products_link_url": "https://www.instacart.com/store/list/integration"})
    attach_transport(monkeypatch, handler)
    for _ in range(2):
        response = post(web, "/grocery/instacart", {"plan_id": saved["id"]})
        assert response.status_code == 303
        assert response.headers["location"] == "https://www.instacart.com/store/list/integration"
    assert len(bodies) == 1
    assert {i["name"] for i in bodies[0]["line_items"]} == {i["name"] for i in items[1:]}
    assert bodies[0]["link_type"] == "shopping_list" and bodies[0]["expires_in"] == 7
    assert all("quantity" not in row for row in bodies[0]["line_items"])
    assert snapshot(application)["settings"]["instacart"]["url"] == response.headers["location"]
    assert post(web, "/grocery/toggle", {"key": first["key"], "checked": "false", "plan_id": saved["id"]}).status_code == 204
    assert post(web, "/grocery/instacart", {"plan_id": saved["id"]}).status_code == 303
    assert len(bodies) == 2 and len(bodies[1]["line_items"]) == len(items)


@pytest.mark.parametrize("failure,reason", [
    ("timeout", "provider"), ("unauthorized", "provider"), ("malformed_json", "provider"),
    ("missing_url", "response"), ("untrusted_url", "response"), ("redirect", "provider"),
])
def test_failed_provider_keeps_list_and_never_redirects_to_untrusted_location(application, web, monkeypatch, failure, reason):
    onboard(web)
    generate(web)
    before = snapshot(application)
    items = shopping(application, before["id"])
    calls = []
    def handler(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ConnectTimeout("integration-shopping-key", request=request)
        if failure == "unauthorized":
            return httpx.Response(401, text="integration-shopping-key")
        if failure == "malformed_json":
            return httpx.Response(200, text="integration-shopping-key")
        if failure == "redirect":
            return httpx.Response(302, headers={"Location": "https://evil.example.test"})
        return httpx.Response(200, json={} if failure == "missing_url" else {"products_link_url": "https://instacart.com.evil.example.test/list"})
    attach_transport(monkeypatch, handler)
    response = post(web, "/grocery/instacart", {"plan_id": before["id"]})
    assert response.status_code == 303 and response.headers["location"] == "/grocery?handoff=" + reason
    page = web.get(response.headers["location"])
    assert page.status_code == 200 and "integration-shopping-key" not in page.text
    assert len(calls) == 1
    assert snapshot(application) == before
    assert shopping(application, before["id"]) == items


def test_empty_list_and_missing_key_do_not_call_provider(application, web, monkeypatch):
    onboard(web)
    generate(web)
    saved = snapshot(application)
    assert post(web, "/grocery/instacart", {"plan_id": saved["id"]}).headers["location"] == "/grocery?handoff=unavailable"
    def unexpected(transport, request):
        pytest.fail("Empty shopping lists must not contact a provider")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", unexpected)
    monkeypatch.setenv("INSTACART_API_KEY", "integration-shopping-key")
    for item in shopping(application, saved["id"]):
        assert post(web, "/grocery/toggle", {"key": item["key"], "checked": "true", "plan_id": saved["id"]}).status_code == 204
    response = post(web, "/grocery/instacart", {"plan_id": saved["id"]})
    assert response.status_code == 303 and response.headers["location"] == "/grocery?handoff=empty"
