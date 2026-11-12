"""Authentication, CSRF, ownership, shared rate counters and real startup migrations."""
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from sqlalchemy import inspect, select, text

from app.models import PantryItem, Plan, Profile, SecurityCounter, User
from app.security import verify_password
from tests.integration.helpers import EMAIL, PASSWORD, generate, onboard, post, register, snapshot

pytestmark = pytest.mark.integration


def test_restart_preserves_accounts_profiles_plans_and_grocery_checks(application):
    from tests.integration.helpers import shopping
    with application.client() as first:
        onboard(first, free_text="no fish")
        generate(first)
        saved = snapshot(application)
        item = shopping(application, saved["id"])[0]
        assert post(first, "/grocery/toggle", {"key": item["key"], "checked": "true", "plan_id": saved["id"]}).status_code == 204
        cookies = {"session": first.cookies["session"]}
        tables = set(inspect(application.sessions.kw["bind"]).get_table_names())
        assert {"alembic_version", "users", "password_resets", "security_counters", "plans"} <= tables
    with application.client(cookies) as restarted:
        assert 'id="meals-data"' in restarted.get("/").text
        assert 'checked' in restarted.get("/grocery").text
        assert snapshot(application)["id"] == saved["id"]
    with application.sessions() as db:
        assert db.query(User).count() == 1 and db.query(Plan).count() == 1
        assert db.scalar(select(Profile)).free_text == "no fish"
        assert db.execute(text("SELECT version_num FROM alembic_version")).scalar() == ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
        assert verify_password(PASSWORD, db.scalar(select(User)).password_hash)


def test_real_startup_upgrades_legacy_database_without_losing_existing_login(application):
    from app.security import hash_password
    engine = application.sessions.kw["bind"]
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL, password_hash VARCHAR(255) NOT NULL, created_at DATETIME NOT NULL)"))
        connection.execute(text("INSERT INTO users VALUES (1, :email, :password, '2026-11-01 00:00:00')"),
                           {"email": EMAIL, "password": hash_password(PASSWORD)})
    with application.client() as upgraded:
        assert post(upgraded, "/login", {"email": EMAIL, "password": PASSWORD}).status_code == 303
        assert upgraded.get("/").headers["location"] == "/survey"
        assert post(upgraded, "/survey", {"budget": "200"}).status_code == 303
        generate(upgraded)
    with application.client() as restarted:
        assert post(restarted, "/login", {"email": EMAIL, "password": PASSWORD}).status_code == 303
        assert 'id="meals-data"' in restarted.get("/").text
    with application.sessions() as db:
        assert db.query(User).count() == 1 and db.query(Plan).count() == 1


def test_normalized_duplicate_email_cannot_replace_account_or_password(application, web):
    register(web)
    response = post(web, "/register", {"email": "  INTEGRATION@EXAMPLE.TEST  ", "password": "different-password"})
    assert response.status_code == 400 and "already registered" in response.text
    assert post(web, "/logout").status_code == 303
    assert post(web, "/login", {"email": EMAIL.upper(), "password": PASSWORD}).status_code == 303
    with application.sessions() as db:
        assert db.query(User).count() == 1
        assert db.scalar(select(User)).email == EMAIL
        assert not verify_password("different-password", db.scalar(select(User)).password_hash)


def test_logout_rotates_csrf_and_old_token_cannot_mutate_account(application, web):
    register(web)
    old_token = web.cookies["csrf_token"]
    assert post(web, "/logout").status_code == 303
    assert web.cookies["csrf_token"] != old_token
    rejected = web.post("/register", data={"csrf_token": old_token, "email": "other@example.test", "password": PASSWORD})
    assert rejected.status_code == 403
    with application.sessions() as db:
        assert db.query(User).count() == 1


@pytest.mark.parametrize("operation", ["meal", "plan", "calendar", "pin", "status", "rate", "swap", "feedback", "pantry", "grocery", "checkin", "undo"])
def test_other_account_cannot_read_or_change_owned_resources(application, web, operation):
    onboard(web)
    generate(web)
    assert post(web, "/pantry/add", {"name": "rice", "quantity": "2", "unit": "cup"}).status_code == 303
    before = snapshot(application)
    with application.sessions() as db:
        pantry_id = db.scalar(select(PantryItem.id))
    with application.client() as stranger:
        onboard(stranger, "stranger@example.test")
        generate(stranger)
        meal_id, plan_id = before["meals"][0]["id"], before["id"]
        if operation in {"meal", "plan", "calendar"}:
            path = {"meal": f"/meals/{meal_id}", "plan": f"/plans/{plan_id}", "calendar": f"/plans/{plan_id}/calendar.ics"}[operation]
            assert stranger.get(path).status_code == 404
        elif operation in {"pin", "status", "rate", "swap"}:
            response = post(stranger, f"/meals/{meal_id}/{operation}", {"status": "cooked", "rating": "5"})
            assert response.status_code == 404
        elif operation == "feedback":
            assert post(stranger, "/feedback", {"plan_id": plan_id, "plan_correct": "yes"}).status_code == 404
        elif operation == "pantry":
            assert post(stranger, f"/pantry/{pantry_id}/delete").status_code == 303
        elif operation == "grocery":
            assert post(stranger, "/grocery/toggle", {"plan_id": plan_id, "key": "rice|cup", "checked": "true"}).status_code == 409
        elif operation == "checkin":
            assert post(stranger, "/checkin", {"plan_id": plan_id, "bought_all": "true"}).status_code == 409
        else:
            assert post(stranger, "/checkin/undo", {"plan_id": plan_id}).status_code == 409
    assert snapshot(application) == before
    with application.sessions() as db:
        assert db.get(PantryItem, pantry_id).quantity == 2


@pytest.mark.parametrize("path,data", [
    ("/survey", {"budget": "150"}), ("/plan/generate", {}),
    ("/pantry/add", {"name": "rice"}), ("/preferences/lifestyle", {}),
    ("/prices", {"key": "rice|cup", "quantity": "1", "price": "1", "source": "test", "observed_on": "2026-11-01"}),
    ("/feedback", {}), ("/checkin", {}),
])
def test_anonymous_csrf_valid_mutation_redirects_without_writing(application, web, path, data):
    response = post(web, path, data)
    assert response.status_code == 303 and response.headers["location"] == "/login"
    with application.sessions() as db:
        assert db.query(User).count() == db.query(Plan).count() == db.query(PantryItem).count() == 0


def test_auth_limit_survives_a_new_http_client(application, web, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("AUTH_RATE_LIMIT", "1")
    assert post(web, "/login", {"email": EMAIL, "password": "wrong"}).status_code == 401
    with application.client() as other:
        response = post(other, "/login", {"email": EMAIL, "password": "wrong"})
        assert response.status_code == 429
        assert 1 <= int(response.headers["Retry-After"]) <= 900
    with application.sessions() as db:
        assert db.scalar(select(SecurityCounter)).count == 2
        assert db.query(User).count() == 0


def test_generation_limit_is_per_account_and_blocks_before_new_plan(application, web, monkeypatch):
    onboard(web)
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("GENERATION_RATE_LIMIT", "1")
    generate(web)
    saved = snapshot(application)
    assert post(web, "/plan/regenerate").status_code == 429
    assert snapshot(application) == saved
    with application.client() as other:
        onboard(other, "quota-other@example.test")
        generate(other)
        assert snapshot(application, "quota-other@example.test")["user_id"] != saved["user_id"]


def test_tampered_signed_session_cannot_open_a_private_plan(application, web):
    onboard(web)
    generate(web)
    saved = snapshot(application)
    session = web.cookies["session"]
    # Change signed payload bytes, leaving the signature untouched.
    session = ("A" if session[0] != "A" else "B") + session[1:]
    with application.client({"session": session}) as attacker:
        response = attacker.get(f'/plans/{saved["id"]}/calendar.ics')
        assert response.status_code == 303 and response.headers["location"] == "/login"
    assert snapshot(application) == saved
