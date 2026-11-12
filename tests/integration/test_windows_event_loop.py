"""Reproduce Windows' TCP-backed socketpair on any supported test platform."""
import socket

import pytest

from tests.integration.helpers import generate, onboard, snapshot

pytestmark = pytest.mark.integration


@pytest.fixture
def windows_application(monkeypatch, request):
    # CPython uses this loopback TCP implementation for Windows' event-loop pipe.
    # Install it before the application fixture captures/guards socketpair.
    monkeypatch.setattr(socket, "socketpair", socket._fallback_socketpair)
    return request.getfixturevalue("application")


def test_windows_tcp_socketpair_starts_app_without_allowing_application_network(windows_application):
    with windows_application.client() as client:
        onboard(client)
        generate(client)
        assert len(snapshot(windows_application)["meals"]) == 21

    # Asyncio can exchange wake-up bytes through the protected socketpair.
    left, right = socket.socketpair()
    try:
        left.settimeout(1)
        right.settimeout(1)
        left.sendall(b"wake")
        assert right.recv(4) == b"wake"
    finally:
        left.close()
        right.close()

    # The narrow socketpair allowance must not leak to ordinary connections.
    for address in ("127.0.0.1", "203.0.113.1"):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.1)
            with pytest.raises(AssertionError, match="must not make real network"):
                sock.connect((address, 443))
    with pytest.raises(AssertionError, match="must not make real network"):
        socket.create_connection(("127.0.0.1", 443))
