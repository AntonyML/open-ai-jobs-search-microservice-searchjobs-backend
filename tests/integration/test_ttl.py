"""TTL: limpieza de ofertas expiradas por ingested_at (no por expires_at)."""

from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import select

from app.models import JobPosting
from app.ttl import clean_expired_jobs

from tests.factories import make_job_posting

pytestmark = pytest.mark.integration


async def _remaining(db) -> list[JobPosting]:
    result = await db.execute(select(JobPosting))
    return list(result.scalars().all())


async def test_removes_only_jobs_older_than_cutoff(db_session):
    now = datetime.now(timezone.utc)
    old = make_job_posting(title="Expired", ingested_at=now - timedelta(hours=100))
    fresh = make_job_posting(title="Fresh", ingested_at=now - timedelta(hours=2))
    db_session.add_all([old, fresh])
    await db_session.commit()

    await clean_expired_jobs(db_session, ttl_hours=24)

    remaining = await _remaining(db_session)
    assert len(remaining) == 1
    assert remaining[0].title == "Fresh"


async def test_cuts_off_by_ingested_at_not_expires_at(db_session):
    now = datetime.now(timezone.utc)
    job = make_job_posting(
        title="Old but not expired",
        ingested_at=now - timedelta(hours=100),
        expires_at=now + timedelta(hours=72),
    )
    db_session.add(job)
    await db_session.commit()

    await clean_expired_jobs(db_session, ttl_hours=24)

    assert await _remaining(db_session) == []


async def test_keeps_fresh_jobs(db_session):
    now = datetime.now(timezone.utc)
    db_session.add(make_job_posting(ingested_at=now))
    await db_session.commit()

    await clean_expired_jobs(db_session, ttl_hours=24)

    assert len(await _remaining(db_session)) == 1


async def test_empty_table_is_safe(db_session):
    await clean_expired_jobs(db_session, ttl_hours=24)
    assert await _remaining(db_session) == []