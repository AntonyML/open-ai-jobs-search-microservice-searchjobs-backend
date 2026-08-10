from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.engine import make_url


class Base(DeclarativeBase):
    pass


_engine = None
async_session_maker: async_sessionmaker[AsyncSession] | None = None


async def init_db(database_url: str):
    global _engine, async_session_maker
    # QueuePool-only args (pool_size/max_overflow/pool_timeout) no aplican a
    # SQLite (StaticPool); gatearlos evita TypeError en tests y dev local.
    url = make_url(database_url)
    pool_kwargs = {}
    if not url.get_backend_name().startswith("sqlite"):
        pool_kwargs.update(
            pool_size=3,
            max_overflow=2,
            pool_timeout=30,
            pool_recycle=1800,
            pool_pre_ping=True,
        )
    _engine = create_async_engine(database_url, echo=False, **pool_kwargs)
    async_session_maker = async_sessionmaker(
        _engine, class_=AsyncSession, expire_on_commit=False
    )


async def create_tables():
    """Only used for tests with SQLite in-memory. Production uses Alembic."""
    global _engine
    if _engine:
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)


async def close_db():
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None


async def get_session():
    assert async_session_maker is not None, "Database not initialized"
    async with async_session_maker() as session:
        yield session
