"""Lifecycle de la app (app.main): startup, shutdown y ttl_loop.

Frontera mockeada: Telegram (_StubTelegram). La DB se ejercita de verdad
(init_db/close_db de app.database sobre SQLite en memoria) salvo donde se
indica. El objetivo es comportamiento observable, no detalles internos.
"""

import asyncio
import logging
import os
import tempfile
import time
from datetime import datetime, timezone, timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import main as main_mod
from app import database as database_mod
from app.models import JobPosting

from tests.factories import FakeTelegram, make_job_posting

pytestmark = pytest.mark.integration


class _StubTelegram(FakeTelegram):
    """FakeTelegram que registra start/stop (la frontera real no puede usarse)."""

    def __init__(self):
        super().__init__()
        self.started = False
        self.stopped = False

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True


class _Clock:
    """Resultado del fixture fast_clock: sleeps reales + argumentos capturados."""

    def __init__(self, sleep_calls, real_sleep):
        self.sleep_calls = sleep_calls
        self.real_sleep = real_sleep


@pytest.fixture
def fast_clock(monkeypatch):
    """Sustituye asyncio.sleep por un sleep inmediato que registra la duración.

    Evita esperar el intervalo real de TTL (minutos) en los tests y permite
    cancelar el loop desde afuera en pocas iteraciones.
    """
    real_sleep = asyncio.sleep
    sleep_calls = []

    async def _fake_sleep(seconds, result=None):
        sleep_calls.append(seconds)
        await real_sleep(0, result=result)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    return _Clock(sleep_calls, real_sleep)


def _use_sqlite_settings(monkeypatch, with_telegram_credentials: bool):
    monkeypatch.setattr(
        main_mod.settings, "database_url", "sqlite+aiosqlite://", raising=False
    )
    if with_telegram_credentials:
        monkeypatch.setattr(main_mod.settings, "telegram_api_id", 123456)
        monkeypatch.setattr(main_mod.settings, "telegram_api_hash", "test-hash")
    else:
        monkeypatch.setattr(main_mod.settings, "telegram_api_id", 0)
        monkeypatch.setattr(main_mod.settings, "telegram_api_hash", "")


async def _make_isolated_db():
    """Motor + maker sobre un SQLite temporal aislado y determinista.

    El loop corre como tarea concurrente compartiendo sesiones con el test;
    un archivo evita las carreras de identidad de las bases en memoria (donde
    cada conexión aislada pierde el esquema a mitad de test).
    """
    path = tempfile.mktemp(suffix=".db")
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(database_mod.Base.metadata.create_all)

    async def _cleanup():
        await engine.dispose()
        if os.path.exists(path):
            os.remove(path)

    return maker, _cleanup


async def _pump(clock, predicate, timeout=2.0):
    """Cede turnos reales del event-loop hasta que predicate() sea verdadera.

    Necesario porque el loop TTL avanza por turns y sus operaciones aiosqlite
    no terminan en un número fijo de yields. Usa el sleep REAL (no el patched)
    para no contaminar fast_clock.sleep_calls.
    """
    import inspect

    end = time.time() + timeout
    while time.time() < end:
        result = predicate()
        if inspect.isawaitable(result):
            result = await result
        if result:
            return True
        await clock.real_sleep(0)
    return False


class TestLifespan:
    """Contrato del lifecycle de la app."""

    async def test_startup_initializes_db_and_cancels_ttl_on_shutdown(
        self, monkeypatch, caplog
    ):
        _use_sqlite_settings(monkeypatch, with_telegram_credentials=True)
        telegram = _StubTelegram()
        monkeypatch.setattr(main_mod, "telegram", telegram)

        ttl_started = asyncio.Event()
        ttl_cancelled = asyncio.Event()

        async def _blocking_ttl_loop():
            ttl_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                ttl_cancelled.set()
                raise

        monkeypatch.setattr(main_mod, "ttl_loop", _blocking_ttl_loop)

        async with main_mod.lifespan(FastAPI()) as _:
            await asyncio.wait_for(ttl_started.wait(), timeout=1)

            # startup inicializa la DB y conecta Telegram
            assert database_mod.async_session_maker is not None
            assert telegram.started is True

        # shutdown: se crea la tarea TTL y se cancela; Telegram y DB se cierran
        await asyncio.wait_for(ttl_cancelled.wait(), timeout=1)
        assert telegram.stopped is True
        assert database_mod._engine is None

    async def test_startup_without_telegram_credentials_warns_and_skips_start(
        self, monkeypatch, caplog
    ):
        caplog.set_level(logging.WARNING)
        _use_sqlite_settings(monkeypatch, with_telegram_credentials=False)
        telegram = _StubTelegram()
        monkeypatch.setattr(main_mod, "telegram", telegram)

        ttl_started = asyncio.Event()

        async def _blocking_ttl_loop():
            ttl_started.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(main_mod, "ttl_loop", _blocking_ttl_loop)

        async with main_mod.lifespan(FastAPI()) as _:
            await asyncio.wait_for(ttl_started.wait(), timeout=1)
            assert telegram.started is False

        assert "telegram_not_configured" in caplog.text
        assert telegram.stopped is True
        assert database_mod._engine is None

    async def test_shutdown_tolerates_already_finished_ttl_task(
        self, monkeypatch
    ):
        _use_sqlite_settings(monkeypatch, with_telegram_credentials=True)
        telegram = _StubTelegram()
        monkeypatch.setattr(main_mod, "telegram", telegram)

        async def _done_ttl_loop():
            return

        monkeypatch.setattr(main_mod, "ttl_loop", _done_ttl_loop)

        async with main_mod.lifespan(FastAPI()) as _:
            await asyncio.sleep(0)
            # la tarea TTL ya terminó antes del shutdown
            pending = [
                t for t in asyncio.all_tasks()
                if t.get_coro().__name__ == "_done_ttl_loop"
            ]
            assert pending == []

        assert telegram.stopped is True
        assert database_mod._engine is None


class TestTtlLoop:
    """Comportamiento real de ttl_loop sobre una base aislada determinista."""

    async def test_runs_cleanup_periodically_and_deletes_expired(
        self, monkeypatch, fast_clock
    ):
        maker, cleanup = await _make_isolated_db()
        monkeypatch.setattr(database_mod, "async_session_maker", maker)
        monkeypatch.setattr(main_mod.settings, "job_ttl_hours", 24)
        monkeypatch.setattr(main_mod.settings, "ttl_cleanup_interval_minutes", 60)
        try:
            now = datetime.now(timezone.utc)
            async with maker() as db:
                db.add(make_job_posting(
                    title="Expired", ingested_at=now - timedelta(hours=100),
                ))
                db.add(make_job_posting(
                    title="Fresh", ingested_at=now - timedelta(hours=2),
                ))
                await db.commit()

            task = asyncio.create_task(main_mod.ttl_loop())

            async def _expired_deleted():
                async with maker() as db:
                    titles = {
                        j.title
                        for j in (await db.execute(select(JobPosting))).scalars().all()
                    }
                return titles == {"Fresh"}

            removed = await _pump(fast_clock, _expired_deleted)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

            # duerme (en cada ciclo) exactamente el intervalo configurado (60 min)
            assert fast_clock.sleep_calls
            assert fast_clock.sleep_calls == [3600] * len(fast_clock.sleep_calls)

            assert removed, "el loop no llegó a eliminar la fila expirada"
            async with maker() as db:
                titles = {
                    j.title
                    for j in (await db.execute(select(JobPosting))).scalars().all()
                }
            assert titles == {"Fresh"}
        finally:
            await cleanup()

    async def test_survives_cleanup_failure_and_keeps_running(
        self, monkeypatch, fast_clock
    ):
        maker, cleanup = await _make_isolated_db()
        monkeypatch.setattr(database_mod, "async_session_maker", maker)
        calls = {"n": 0}

        async def _flaky_cleanup(db, ttl_hours):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("db hiccup")

        monkeypatch.setattr(main_mod, "clean_expired_jobs", _flaky_cleanup)

        try:
            task = asyncio.create_task(main_mod.ttl_loop())
            ran_twice = await _pump(fast_clock, lambda: calls["n"] >= 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

            # el fallo no detiene el loop: el siguiente ciclo vuelve a limpiar
            assert ran_twice, f"el loop se detuvo tras el fallo (llamadas={calls['n']})"
            assert calls["n"] >= 2
        finally:
            await cleanup()

    async def test_skips_cleanup_when_db_not_initialized(
        self, monkeypatch, fast_clock
    ):
        monkeypatch.setattr(database_mod, "async_session_maker", None)
        calls = {"n": 0}

        async def _counting_cleanup(db, ttl_hours):
            calls["n"] += 1

        monkeypatch.setattr(main_mod, "clean_expired_jobs", _counting_cleanup)

        task = asyncio.create_task(main_mod.ttl_loop())
        for _ in range(6):
            await fast_clock.real_sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # sin DB inicializada el loop sigue vivo pero nunca limpia
        assert fast_clock.sleep_calls
        assert calls["n"] == 0