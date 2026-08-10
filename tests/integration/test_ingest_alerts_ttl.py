"""Regresión: alerta "all groups down" y filtro TTL de ofertas recientes.

Cubre dos huecos que dejaban pasar bugs silenciosos:
1. Cuando TODOS los grupos de una categoría fallan en la misma corrida y la
   categoría tiene admin_alert_email, se debe enviar la alerta por email.
2. _get_recent_jobs debe excluir ofertas expiradas (expires_at <= now) y
   respetar el límite.
"""

from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import select

from app.ingestion import IngestOrchestrator
from app.models import JobPosting

from tests.factories import FakeTelegram, make_job_posting

pytestmark = pytest.mark.integration


def _alert_category() -> dict:
    return {
        "label": "Test Category",
        "search_keywords": ["test"],
        "groups": [
            {
                "id": "g1",
                "name": "G1",
                "telegram_channel": "chan1",
                "priority": 1,
                "format_template": "freetext",
                "status": "active",
                "consecutive_failures": 0,
            },
            {
                "id": "g2",
                "name": "G2",
                "telegram_channel": "chan2",
                "priority": 2,
                "format_template": "freetext",
                "status": "active",
                "consecutive_failures": 0,
            },
        ],
        "admin_alert_email": "admin@acme.com",
        "demand_score": 0,
        "last_polled": None,
        "poll_interval_hours": 24,
    }


async def test_all_groups_failed_sends_admin_alert(db_session, monkeypatch):
    """Regression: con todos los grupos caídos y email configurado, se alerta
    al admin con el asunto y los detalles de fallo — no solo un log silencioso."""
    import app.ingestion as ingestion

    monkeypatch.setattr(ingestion, "GROUP_REGISTRY", {"test_cat": _alert_category()})

    called = {}

    async def fake_alert(email, subject, body, **kwargs):
        called.update(email=email, subject=subject, body=body)

    monkeypatch.setattr(ingestion, "send_admin_alert", fake_alert)

    fake = FakeTelegram(errors={
        "chan1": ConnectionError("down"),
        "chan2": ConnectionError("down"),
    })
    orch = IngestOrchestrator(fake)
    jobs = await orch.fetch_from_category("test_cat", db_session)

    assert jobs == []
    assert called["email"] == "admin@acme.com"
    assert called["subject"] == "All groups down for 'Test Category'"
    assert "chan1" in called["body"]
    assert "chan2" in called["body"]


async def test_all_groups_failed_without_admin_email_is_silent(db_session, monkeypatch):
    """Sin admin_alert_email la ingesta falla en silencio (log), sin llamada a alerta."""
    import app.ingestion as ingestion

    cat = _alert_category()
    cat["admin_alert_email"] = ""
    monkeypatch.setattr(ingestion, "GROUP_REGISTRY", {"test_cat": cat})

    calls = []

    async def fake_alert(*args, **kwargs):
        calls.append(args)

    monkeypatch.setattr(ingestion, "send_admin_alert", fake_alert)

    fake = FakeTelegram(errors={
        "chan1": ConnectionError("down"),
        "chan2": ConnectionError("down"),
    })
    orch = IngestOrchestrator(fake)
    jobs = await orch.fetch_from_category("test_cat", db_session)

    assert jobs == []
    assert calls == []


async def test_all_groups_failed_still_marks_down_after_threshold(db_session, monkeypatch):
    """Con fallos repetidos >= MAX_CONSECUTIVE_FAILURES los grupos se marcan
    'down' y se registra GroupHealth — incluso sin email de alerta."""
    import app.ingestion as ingestion

    from app.models import GroupHealth

    cat = _alert_category()
    cat["admin_alert_email"] = ""
    monkeypatch.setattr(ingestion, "GROUP_REGISTRY", {"test_cat": cat})

    fake = FakeTelegram(errors={
        "chan1": ConnectionError("down"),
        "chan2": ConnectionError("down"),
    })
    orch = IngestOrchestrator(fake)

    for _ in range(3):
        await orch.fetch_from_category("test_cat", db_session)

    assert cat["groups"][0]["status"] == "down"
    assert cat["groups"][0]["consecutive_failures"] == 3

    result = await db_session.execute(
        select(GroupHealth).where(GroupHealth.group_id == "g1")
    )
    health = result.scalars().all()
    assert health
    assert health[-1].status == "down"


async def test_get_recent_jobs_excludes_expired_and_orders_desc(db_session):
    """Regression: las ofertas expiradas no deben devolverse; el resto se ordena
    por ingested_at descendente (las más nuevas primero)."""
    now = datetime.now(timezone.utc)
    fresh = make_job_posting(
        category_id="test_cat", title="Fresh",
        ingested_at=now - timedelta(hours=1),
        expires_at=now + timedelta(hours=72),
    )
    older = make_job_posting(
        category_id="test_cat", title="Older",
        ingested_at=now - timedelta(hours=5),
        expires_at=now + timedelta(hours=72),
    )
    expired = make_job_posting(
        category_id="test_cat", title="Expired",
        ingested_at=now - timedelta(hours=10),
        expires_at=now - timedelta(hours=1),
    )
    other_cat = make_job_posting(
        category_id="other", title="Other",
        ingested_at=now,
        expires_at=now + timedelta(hours=72),
    )
    db_session.add_all([fresh, older, expired, other_cat])
    await db_session.commit()

    orch = IngestOrchestrator(FakeTelegram())
    jobs = await orch._get_recent_jobs(db_session, "test_cat")

    assert [j.title for j in jobs] == ["Fresh", "Older"]


async def test_get_recent_jobs_respects_limit(db_session):
    now = datetime.now(timezone.utc)
    db_session.add_all([
        make_job_posting(
            category_id="test_cat", title=f"Job {i}",
            ingested_at=now - timedelta(minutes=i),
            expires_at=now + timedelta(hours=72),
        )
        for i in range(3)
    ])
    await db_session.commit()

    orch = IngestOrchestrator(FakeTelegram())
    jobs = await orch._get_recent_jobs(db_session, "test_cat", limit=2)

    assert len(jobs) == 2
    assert jobs[0].title == "Job 0"  # más reciente primero
    assert jobs[1].title == "Job 1"
