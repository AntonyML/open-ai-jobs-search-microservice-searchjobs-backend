"""Check alembic state and tables."""
import asyncio
from sqlalchemy import text
import app.database as db_mod
from app.config import settings


async def check():
    await db_mod.init_db(settings.database_url)
    maker = db_mod.async_session_maker
    async with maker() as db:
        tables = await db.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        )
        all_tables = [r[0] for r in tables.all()]
        print("Tables:", sorted(all_tables))

        if "alembic_version" in all_tables:
            versions = await db.execute(text("SELECT * FROM alembic_version"))
            print("Alembic versions:", versions.all())
        else:
            print("No alembic_version table")

        for t in ["ingested_jobs", "ingest_jobs", "group_health"]:
            print(f"  {t}: {'EXISTS' if t in all_tables else 'MISSING'}")

    await db_mod.close_db()


asyncio.run(check())
