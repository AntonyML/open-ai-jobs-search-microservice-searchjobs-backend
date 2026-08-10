"""send_admin_alert: contrato con Resend (HTTP) y fallos silenciosos.

La alerta POSTea a https://api.resend.com/emails y nunca propaga errores:
sin email o sin API key solo registra logs; fallos de red se capturan.
"""

import logging

import httpx
import pytest

from app.alert import send_admin_alert

pytestmark = pytest.mark.unit


async def test_empty_email_returns_silently(caplog):
    await send_admin_alert(email="", subject="S", body="B")
    assert "No admin email configured" in caplog.text


async def test_without_resend_key_logs_alert(caplog):
    caplog.set_level(logging.INFO)
    await send_admin_alert(email="admin@acme.com", subject="Subject", body="Body")
    assert "Resend not configured" in caplog.text


class _FakeClient:
    """Reemplazo de httpx.AsyncClient: captura el POST y controla la respuesta."""

    def __init__(self, captured: dict, status: int = 200, error: Exception | None = None):
        self.captured = captured
        self.status = status
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        if self.error:
            raise self.error
        request = httpx.Request("POST", url, headers=headers or {}, json=json)
        response = httpx.Response(self.status, request=request)
        self.captured.update(url=url, headers=headers, json=json)
        return response


async def test_posts_to_resend_with_expected_payload(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    captured = {}
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeClient(captured))

    await send_admin_alert(
        email="admin@acme.com",
        subject="All groups down",
        body="Line one\nLine two",
        resend_api_key="key-123",
        resend_from_email="jobs@acme.com",
    )

    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["headers"]["Authorization"] == "Bearer key-123"
    assert captured["json"]["to"] == ["admin@acme.com"]
    assert captured["json"]["subject"] == "All groups down"
    assert captured["json"]["from"] == "Jobs Ingest <jobs@acme.com>"
    assert "<pre>Line one<br>Line two</pre>" in captured["json"]["html"]
    assert "Alert sent to admin@acme.com" in caplog.text


async def test_swallows_resend_failure(caplog, monkeypatch):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: _FakeClient({}, error=httpx.ConnectError("down")),
    )

    await send_admin_alert(
        email="admin@acme.com", subject="S", body="B", resend_api_key="k"
    )

    assert "Failed to send alert to admin@acme.com" in caplog.text