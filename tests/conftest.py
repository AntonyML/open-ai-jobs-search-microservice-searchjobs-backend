"""Fixtures compartidas por toda la suite.

Regla: este archivo contiene SOLO infraestructura de test transversal:

- db_engine / session_factory / db_session: base de datos aislada por test.
- api_client: aplicación FastAPI con dependencias override + orquestador stub.

Lo que NO vive aquí:
- Mensajes reales de Telegram           -> tests/fixtures.py
- Fakes (FakeTelegram, FakeOrchestrator) -> tests/factories.py
- Datos o lógica de un dominio concreto  -> junto a los tests que lo usan.
"""

import os

import httpx
import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sqlalchemy.pool import StaticPool

from app.database import Base, get_session
from app.main import create_app

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "sqlite+aiosqlite://"
)


def _make_engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        return {
            "poolclass": StaticPool,
            "connect_args": {"check_same_thread": False},
        }
    return {}


@pytest.fixture
async def db_engine():
    """Motor async aislado por test.

    Por defecto SQLite en memoria (pool único de una conexión, por lo que la
    base vive mientras el motor exista). Apuntable a PostgreSQL real vía
    TEST_DATABASE_URL sin cambiar la estrategia de los tests.
    """
    url = TEST_DATABASE_URL
    engine = create_async_engine(url, **_make_engine_kwargs(url))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(db_engine):
    """Factory de sesiones async ligada al motor de test."""
    return async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )


@pytest.fixture
async def db_session(session_factory):
    """Sesión async lista para usar en tests de integración."""
    async with session_factory() as session:
        yield session


@pytest.fixture
async def api_client(db_engine, session_factory, monkeypatch):
    """Cliente HTTP contra la app real (routes + DB), externos mockeados.

    Usa httpx.ASGITransport con la app que produce create_app(); el lifespan
    (Telegram/DB real) NO se ejecuta porque no se entra en el context manager
    de la app. La dependencia get_session se sobreescribe para usar la DB de
    test y el orquestador se sustituye por FakeOrchestrator en la frontera.
    """
    from tests.factories import FakeOrchestrator

    app = create_app()

    async def _override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session

    fake_orchestrator = FakeOrchestrator(session_factory)
    monkeypatch.setattr("app.routes.get_orch", lambda: fake_orchestrator)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        yield client, fake_orchestrator