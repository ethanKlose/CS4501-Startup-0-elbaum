"""Paid tests require --run-live and never use tests/conftest.py's fake-key fixtures."""
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import SimpleNamespace

import pytest
from dotenv import dotenv_values

from live_tests.cost_guard import CallBudget

ROOT = Path(__file__).resolve().parents[1]
CASES = {"smoke": "test_live_credentials_and_json", "week": "test_live_weekly_workflow",
         "restricted": "test_live_vegetarian_plan"}


def pytest_addoption(parser):
    group = parser.getgroup("paid OpenAI tests")
    group.addoption("--run-live", action="store_true", help="Explicitly permit real paid OpenAI requests")
    group.addoption("--live-case", choices=[*CASES, "all"], default="smoke")
    group.addoption("--live-max-calls", type=int, default=2)
    group.addoption("--live-budget-usd", default="0.05")


def pytest_configure(config):
    config.addinivalue_line("markers", "live: explicitly opted-in real paid OpenAI test")
    config._paid_outcomes = []
    if config.getoption("--run-live") and hasattr(config, "workerinput"):
        raise pytest.UsageError("Run paid tests without pytest-xdist; the budget is shared within one process")


def pytest_collection_modifyitems(config, items):
    selected, omitted = [], []
    for item in items:
        if "live" not in item.keywords:
            selected.append(item)
        elif not config.getoption("--run-live"):
            item.add_marker(pytest.mark.skip(reason="Paid requests disabled; requires --run-live"))
            selected.append(item)
        elif config.getoption("--live-case") == "all" or item.name == CASES[config.getoption("--live-case")]:
            selected.append(item)
        else:
            omitted.append(item)
    items[:] = selected
    if omitted:
        config.hook.pytest_deselected(items=omitted)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    result = yield
    report = result.get_result()
    if "live" in item.keywords and (report.when == "call" or (report.when == "setup" and report.outcome != "passed")):
        item.config._paid_outcomes.append(dict(test=item.name, phase=report.when, outcome=report.outcome))


@pytest.fixture(scope="session")
def live_budget(pytestconfig):
    if not pytestconfig.getoption("--run-live"):
        pytest.skip("Paid tests require explicit --run-live")
    values = dotenv_values(ROOT / ".env")
    model = (values.get("OPENAI_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()
    try:
        budget = CallBudget(model, max_calls=pytestconfig.getoption("--live-max-calls"),
                            budget_usd=Decimal(pytestconfig.getoption("--live-budget-usd")))
    except (ValueError, InvalidOperation) as exc:
        raise pytest.UsageError(str(exc)) from None
    if pytestconfig.getoption("--live-case") == "all" and budget.max_calls < 3:
        raise pytest.UsageError("All three paid cases require --live-max-calls 3; start with one case instead")
    yield budget
    budget.write_report(ROOT / "test-results/live-openai-report.json", pytestconfig._paid_outcomes)
    print(f"\nLive API attempts: {len(budget.calls)}/{budget.max_calls}; "
          f"reserved estimate: ${float(budget.reserved_usd):.6f}. "
          "Report: test-results/live-openai-report.json")


@pytest.fixture
def real_app(tmp_path, monkeypatch, live_budget):
    if len(live_budget.calls) >= live_budget.max_calls:
        pytest.skip("Shared paid-call cap already consumed; run this scenario separately")
    values = dotenv_values(ROOT / ".env")
    key = (values.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        pytest.fail("Set OPENAI_API_KEY in the repository .env before running live tests", pytrace=False)
    for name in ("OPENAI_BASE_URL", "OPENAI_ORG_ID", "OPENAI_PROJECT_ID", "ANTHROPIC_API_KEY", "INSTACART_API_KEY", "SMTP_HOST"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", key)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("OPENAI_MODEL", live_budget.model)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SECRET_KEY", "isolated-paid-test-session-secret-never-for-production")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "0")
    monkeypatch.setenv("TIMEZONE", "America/New_York")
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", str(live_budget.output_limit))
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "20")
    monkeypatch.setenv("LOCAL_MAIL_DIR", str(tmp_path / "outbox"))
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + (tmp_path / "live.db").as_posix())

    import httpx
    import openai
    if issubclass(openai.DefaultHttpxClient, httpx.Client):
        sdk_http = httpx
    else:
        import httpx2 as sdk_http
    original = sdk_http.HTTPTransport.handle_request
    # Delegate to the original real transport; no response is fabricated here.
    monkeypatch.setattr(sdk_http.HTTPTransport, "handle_request", live_budget.forwarding_handler(original))

    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker
    from app import db as database
    from app.main import create_app
    engine = database.make_engine(os.environ["DATABASE_URL"])
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessions)
    app = create_app()
    assert not app.dependency_overrides
    try:
        with TestClient(app, follow_redirects=False) as web:
            yield SimpleNamespace(web=web, sessions=sessions, budget=live_budget)
    finally:
        engine.dispose()
