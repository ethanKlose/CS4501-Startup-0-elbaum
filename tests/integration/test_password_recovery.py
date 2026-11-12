"""Reset form -> actual mail adapter/outbox -> hashed token -> password/session revocation."""
import hashlib
import json
import ssl
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.models import PasswordReset
from app.routers import recovery
from app.services import mailer
from tests.integration.helpers import EMAIL, PASSWORD, generate, onboard, post, snapshot

pytestmark = pytest.mark.integration


def reset_token(application):
    messages = list((application.directory / "outbox").glob("*.json"))
    assert len(messages) == 1
    mail = json.loads(messages[0].read_text())
    assert mail["to"] == EMAIL and mail["url"].startswith("http://testserver/reset-password?token=")
    return parse_qs(urlparse(mail["url"]).query)["token"][0]


def test_real_local_email_reset_revokes_old_session_and_preserves_owned_data(application, web):
    onboard(web)
    generate(web)
    before = snapshot(application)
    old_session = web.cookies["session"]
    response = post(web, "/forgot-password", {"email": EMAIL})
    assert response.status_code == 200
    token = reset_token(application)
    with application.sessions() as db:
        row = db.scalar(select(PasswordReset))
        assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert token not in row.token_hash and not row.used
    assert token not in response.text
    assert post(web, "/reset-password", {"token": token, "password": "Replacement123!"}).status_code == 303
    assert post(web, "/reset-password", {"token": token, "password": "AnotherPassword123!"}).status_code == 400
    with application.client({"session": old_session}) as stale:
        assert stale.get("/grocery").headers["location"] == "/login"
    assert post(web, "/login", {"email": EMAIL, "password": PASSWORD}).status_code == 401
    assert post(web, "/login", {"email": EMAIL, "password": "Replacement123!"}).status_code == 303
    assert snapshot(application) == before


def test_expired_token_cannot_reset_password(application, web, monkeypatch):
    onboard(web)
    assert post(web, "/forgot-password", {"email": EMAIL}).status_code == 200
    token = reset_token(application)
    with application.sessions() as db:
        expires = db.scalar(select(PasswordReset)).expires_at
    monkeypatch.setattr(recovery, "time", SimpleNamespace(time=lambda: expires + 1))
    response = post(web, "/reset-password", {"token": token, "password": "Replacement123!"})
    assert response.status_code == 400 and "expired" in response.text
    assert post(web, "/login", {"email": EMAIL, "password": PASSWORD}).status_code == 303


def test_unknown_account_has_same_public_response_without_creating_reset_or_mail(application, web):
    onboard(web)
    missing = post(web, "/forgot-password", {"email": "unknown@example.test"})
    with application.sessions() as db:
        assert db.query(PasswordReset).count() == 0
    assert not (application.directory / "outbox").exists()
    known = post(web, "/forgot-password", {"email": EMAIL})
    assert missing.status_code == known.status_code == 200
    assert missing.text == known.text


@pytest.mark.parametrize("port", [587, 465])
def test_smtp_contract_sends_tls_protected_reset_link_usable_by_real_reset_route(application, web, monkeypatch, port):
    onboard(web)
    events, messages = [], []
    monkeypatch.setenv("SMTP_HOST", "mail.example.test")
    monkeypatch.setenv("SMTP_PORT", str(port))
    monkeypatch.setenv("SMTP_USERNAME", "integration-mail-user")
    monkeypatch.setenv("SMTP_PASSWORD", "integration-mail-password")
    class SMTP:
        def __init__(self, host, actual_port, timeout, **kwargs):
            assert (host, actual_port, timeout) == ("mail.example.test", port, 15)
            if port == 465:
                assert kwargs["context"].verify_mode == ssl.CERT_REQUIRED and kwargs["context"].check_hostname
            events.append("connect")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            events.append("close")
        def starttls(self, context):
            assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
            events.append("tls")
        def login(self, username, password):
            assert (username, password) == ("integration-mail-user", "integration-mail-password")
            events.append("login")
        def send_message(self, message):
            events.append("send")
            messages.append(message)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL" if port == 465 else "SMTP", SMTP)
    assert post(web, "/forgot-password", {"email": EMAIL}).status_code == 200
    assert events == (["connect", "tls", "login", "send", "close"] if port == 587 else ["connect", "login", "send", "close"])
    assert messages[0]["To"] == EMAIL
    url = next(line for line in messages[0].get_content().splitlines() if line.startswith("http://testserver/"))
    token = parse_qs(urlparse(url).query)["token"][0]
    assert post(web, "/reset-password", {"token": token, "password": "Replacement123!"}).status_code == 303
    assert post(web, "/login", {"email": EMAIL, "password": "Replacement123!"}).status_code == 303


def test_smtp_failure_returns_generic_response_without_logging_provider_secrets(application, web, monkeypatch, caplog):
    onboard(web)
    monkeypatch.setenv("SMTP_HOST", "mail.example.test")
    class BrokenSMTP:
        def __init__(self, *args, **kwargs):
            raise OSError("integration-mail-password")
    monkeypatch.setattr(mailer.smtplib, "SMTP", BrokenSMTP)
    monkeypatch.setenv("SMTP_PORT", "587")
    response = post(web, "/forgot-password", {"email": EMAIL})
    assert response.status_code == 200
    assert "integration-mail-password" not in response.text + caplog.text
    assert "Password reset delivery failed" in caplog.text
