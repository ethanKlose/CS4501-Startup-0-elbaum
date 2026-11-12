"""Shopping, cooking, check-in, inventory, future plans and consented study exports."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

from app.models import CheckIn, Plan
from scripts.export_study import correctness_summary, export
from tests.integration.helpers import generate, onboard, pantry, post, shopping, snapshot

pytestmark = pytest.mark.integration


def test_shopping_cooking_settlement_is_once_only_and_undo_restores_stock(application, web):
    onboard(web)
    generate(web)
    saved = snapshot(application)
    items = shopping(application, saved["id"])
    for item in items:
        assert post(web, "/grocery/toggle", {"plan_id": saved["id"], "key": item["key"], "checked": "true"}).status_code == 204
    # Cook one meal, so the independent balance includes purchases AND consumption.
    meal = saved["meals"][0]
    assert post(web, f'/meals/{meal["id"]}/status', {"status": "cooked"}).status_code == 303
    purchases = snapshot(application)["settings"]["inventory"]["purchases"]
    expected = {(p["name"], p["unit"]): p["quantity"] for p in purchases}
    for ingredient in meal["ingredients"]:
        key = (ingredient["name"].lower(), ingredient["unit"].lower())
        expected[key] = round(max(0, expected.get(key, 0) - ingredient["quantity"]), 2)
    assert post(web, "/checkin", {"plan_id": saved["id"]}).status_code == 303
    balance = pantry(application, saved["user_id"])
    assert balance == pytest.approx({k: v for k, v in expected.items() if v > 0}, abs=0.01)
    assert post(web, "/checkin", {"plan_id": saved["id"], "bought_all": "true"}).status_code == 303
    assert pantry(application, saved["user_id"]) == balance
    assert post(web, "/grocery/toggle", {"key": items[0]["key"], "checked": "false", "plan_id": saved["id"]}).status_code == 409
    assert post(web, f'/meals/{meal["id"]}/status', {"status": "planned"}).status_code == 409
    assert post(web, "/checkin/undo", {"plan_id": saved["id"]}).status_code == 303
    assert all(q == 0 for q in pantry(application, saved["user_id"]).values())
    with application.sessions() as db:
        assert db.query(CheckIn).count() == 0
    assert not snapshot(application)["settings"]["inventory"]["settled"]


def test_undo_preserves_manual_stock_adjustments_after_checkin(application, web):
    onboard(web)
    generate(web)
    saved = snapshot(application)
    assert post(web, "/checkin", {"bought_all": "true"}).status_code == 303
    closed = snapshot(application)
    change = closed["settings"]["inventory"]["changes"][0]
    assert post(web, "/pantry/add", {"name": change["name"], "unit": change["unit"], "quantity": str(change["after"] + 3)}).status_code == 303
    assert post(web, "/checkin/undo", {"plan_id": saved["id"]}).status_code == 303
    assert pantry(application, saved["user_id"])[(change["name"], change["unit"])] == pytest.approx(change["before"] + 3)


def test_two_http_clients_checking_in_concurrently_settle_purchases_once(application, web):
    onboard(web)
    generate(web)
    saved = snapshot(application)
    assert post(web, "/checkin", {"bought_all": "true"}).status_code == 303
    once = pantry(application, saved["user_id"])
    assert post(web, "/checkin/undo", {"plan_id": saved["id"]}).status_code == 303
    with application.client({"session": web.cookies["session"]}) as second:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(post, client, "/checkin", {"plan_id": saved["id"], "bought_all": "true"}) for client in (web, second)]
            assert [f.result().status_code for f in futures] == [303, 303]
    assert pantry(application, saved["user_id"]) == once
    with application.sessions() as db:
        assert db.query(CheckIn).count() == 1


def test_ratings_and_checkin_change_next_week_and_archive_previous_week(application, web):
    onboard(web)
    generate(web)
    original = snapshot(application)
    meal = original["meals"][0]
    assert post(web, f'/meals/{meal["id"]}/status', {"status": "cooked"}).status_code == 303
    assert post(web, f'/meals/{meal["id"]}/rate', {"rating": "1"}).status_code == 303
    assert post(web, "/checkin", {"cook_time": "too_much", "notes": "no fish", "bought_all": "true"}).status_code == 303
    generate(web, "/plan/next-week")
    new = snapshot(application)
    assert new["settings"]["week_start"] == "2026-11-16"
    assert all(day["minutes"] == 30 for day in new["days"])
    assert meal["name"] not in {m["name"] for m in new["meals"]}
    assert new["settings"]["pantry"]
    assert f'/plans/{original["id"]}' in web.get("/plans").text
    assert "Archived plan" in web.get(f'/plans/{original["id"]}').text
    assert post(web, "/checkin/undo", {"plan_id": original["id"]}).status_code == 409


@pytest.mark.parametrize("values", [{"overall": "invalid"}, {"cook_time": "invalid"}, {"variety": "invalid"}, {"notes": "x" * 501}])
def test_rejected_checkin_does_not_partially_buy_or_settle_inventory(application, web, values):
    onboard(web)
    generate(web)
    saved = snapshot(application)
    response = post(web, "/checkin", {"bought_all": "true", **values})
    assert response.status_code == 422
    assert snapshot(application) == saved
    assert pantry(application, saved["user_id"]) == {}
    with application.sessions() as db:
        assert db.query(CheckIn).count() == 0


def test_feedback_export_respects_consent_privacy_and_latest_review_per_account(application, web):
    onboard(web)
    generate(web)
    saved = snapshot(application)
    for consent, outcome in [("false", "yes"), ("true", "yes"), ("true", "no")]:
        response = post(web, "/feedback", {
            "plan_id": saved["id"], "plan_correct": outcome, "consent": consent,
            "failed_constraints": ["schedule"] if outcome == "no" else [],
            "notes": "private-integration-note", "actual_spend": "", "actual_minutes": "", "baseline_minutes": ""})
        assert response.status_code == 303
    with application.sessions() as db:
        report = export(db)
        summary = correctness_summary(db, expected_participants=20)
    assert len(report["results"]) == 2
    assert summary["reviewed_accounts"] == 1 and summary["correct_accounts"] == 0
    assert summary["status"] == "incomplete" and summary["meets_threshold"] is None
    assert report["results"][-1]["failed_constraints"] == ["schedule"]
    assert report["results"][-1]["actual_minutes"] is None
    assert "private-integration-note" not in str(report) and "@example.test" not in str(report)
    assert "automatic_checks" not in str(report) and "notes" not in str(report)


def test_calendar_export_parses_as_complete_events_and_keeps_archived_dates(application, web):
    import datetime as dt
    onboard(web)
    generate(web)
    original = snapshot(application)

    def parse_export():
        response = web.get(f'/plans/{original["id"]}/calendar.ics')
        assert response.status_code == 200 and response.headers["content-type"].startswith("text/calendar")
        assert response.headers["content-disposition"] == f'attachment; filename="platejoy-plan-{original["id"]}.ics"'
        assert response.content.endswith(b"END:VCALENDAR\r\n")
        lines = response.text.split("\r\n")
        assert all(len(line.encode()) <= 75 for line in lines)
        unfolded = []
        for line in lines:
            if line.startswith((" ", "\t")):
                unfolded[-1] += line[1:]
            else:
                unfolded.append(line)
        events, current = [], None
        for line in unfolded:
            if line == "BEGIN:VEVENT":
                assert current is None
                current = {}
            elif line == "END:VEVENT":
                assert current is not None
                events.append(current)
                current = None
            elif current is not None:
                key, value = line.split(":", 1)
                current[key.split(";")[0]] = value
        assert current is None and len(events) >= 21
        assert len({e["UID"] for e in events}) == len(events)
        for event in events:
            assert dt.datetime.strptime(event["DTSTART"], "%Y%m%dT%H%M%S") < dt.datetime.strptime(event["DTEND"], "%Y%m%dT%H%M%S")
        assert {m["name"] for m in original["meals"]} <= {e["SUMMARY"] for e in events}
        return {e["UID"]: (e["DTSTART"], e["DTEND"], e["SUMMARY"]) for e in events}

    exported = parse_export()
    generate(web, "/plan/next-week")
    assert parse_export() == exported
