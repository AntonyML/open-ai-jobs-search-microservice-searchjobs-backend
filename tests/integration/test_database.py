"""Database: ciclo de vida del engine/session global de app.database."""

import pytest
from sqlalchemy import select

import app.database as database
from app.models import JobPosting

pytestmark = pytest.mark.integration


class TestInitDb:

    async def test_init_db_builds_session_maker(self, monkeypatch):
        monkeypatch.setattr(database, "_engine", None)
        monkeypatch.setattr(database, "async_session_maker", None)

        await database.init_db("sqlite+aiosqlite://")

        assert database.async_session_maker is not None

        await database.close_db()
        assert database._engine is None

    async def test_create_tables_creates_schema(self, monkeypatch):
        await database.init_db("sqlite+aiosqlite://")
        await database.create_tables()

        async with database.async_session_maker() as session:
            result = await session.execute(select(JobPosting))
            assert result.scalars().all() == []

        await database.close_db()

    async def test_close_db_is_idempotent(self, monkeypatch):
        await database.init_db("sqlite+aiosqlite://")
        await database.close_db()
        await database.close_db()

    async def test_get_session_without_init_asserts(self, monkeypatch):
        monkeypatch.setattr(database, "async_session_maker", None)
        with pytest.raises(AssertionError):
            async for _ in database.get_session():
                pass