"""Real application wiring, fresh migrated SQLite files, explicit CSRF and no paid calls.

Unlike the older shared in-memory fixture, these tests keep the real get_db
dependency and lifespan. Only environment, time and external I/O are controlled.
"""
import datetime as dt
import socket
from contextlib import contextmanager
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import db as database
from app.main import create_app
from app.services import planner, weeks


@dataclass
class Application:
    app: object
    sessions: object
    directory: object

    @contextmanager
    def client(self, cookies=None):
        # Lifespan applies real Alembic upgrades on each application start.
        with TestClient(self.app, follow_redirects=False, cookies=cookies) as client:
            yield client


@pytest.fixture
def application(tmp_path, monkeypatch):
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN",
                "INSTACART_API_KEY", "SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD",
                "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SECRET_KEY", "isolated-integration-secret-never-for-production")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "0")
    monkeypatch.setenv("TIMEZONE", "America/New_York")
    monkeypatch.setenv("LOCAL_MAIL_DIR", str(tmp_path / "outbox"))
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://testserver")
    url = "sqlite:///" + (tmp_path / "integration.db").as_posix()
    monkeypatch.setenv("DATABASE_URL", url)
    engine = database.make_engine(url)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessions)
    now = dt.datetime(2026, 11, 2, 9, tzinfo=ZoneInfo("America/New_York"))
    monkeypatch.setattr(weeks, "planning_now", lambda: now)
    monkeypatch.setattr(planner, "planning_now", lambda: now)
    monkeypatch.setattr(planner, "planning_today", lambda: now.date())
    monkeypatch.setattr(planner.random, "randint", lambda a, b: 1729)

    def forbid_network(*args, **kwargs):
        raise AssertionError("Integration tests must not make real network connections")

    monkeypatch.setattr(socket, "create_connection", forbid_network)
    original_connect = socket.socket.connect
    def guarded_connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            forbid_network()
        return original_connect(sock, address)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    app = create_app()
    assert app.dependency_overrides == {}, "Integration tests must exercise real application dependencies"
    yield Application(app, sessions, tmp_path)
    engine.dispose()


@pytest.fixture
def web(application):
    with application.client() as client:
        yield client
