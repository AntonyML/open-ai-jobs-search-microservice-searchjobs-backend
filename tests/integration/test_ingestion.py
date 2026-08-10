"""Ingesta: orquestación de canal -> DB (I/O real sobre SQLite en memoria).

Frontera mockeada: Telegram (FakeTelegram). La DB, el TTL y la lógica del
orquestador se ejercitan de verdad.
"""

from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import select

from app.ingestion import IngestOrchestrator
from app.models import JobPosting, IngestJob, GroupHealth
from app.registry import GROUP_REGISTRY

from tests.factories import FakeTelegram, make_message, make_job_posting
from tests.fixtures import STEM_CR_1, STEM_LATAM_1

pytestmark = pytest.mark.integration


def _reset_stem_cr():
    cat = GROUP_REGISTRY["stem_cr"]
    cat["demand_score"] = 0
    cat["last_polled"] = None
    for g in cat["groups"]:
        g["status"] = "active"
        g["consecutive_failures"] = 0
    return cat


class TestShouldFetch:

    def test_unknown_category_returns_false_and_empty_context(self):
        orch = IngestOrchestrator(FakeTelegram())
        should, ctx = orch.should_fetch("does_not_exist")
        assert should is False
        assert ctx == {}

    def test_first_poll_returns_true(self):
        _reset_stem_cr()
        orch = IngestOrchestrator(FakeTelegram())
        should, ctx = orch.should_fetch("stem_cr")
        assert should is True
        assert ctx.get("label") == "STEM Costa Rica"

    def test_recent_poll_returns_false(self):
        cat = _reset_stem_cr()
        cat["last_polled"] = datetime.now(timezone.utc)
        orch = IngestOrchestrator(FakeTelegram())
        should, _ = orch.should_fetch("stem_cr")
        assert should is False

    def test_poll_after_interval_returns_true(self):
        cat = _reset_stem_cr()
        cat["last_polled"] = datetime.now(timezone.utc) - timedelta(hours=25)
        orch = IngestOrchestrator(FakeTelegram())
        should, _ = orch.should_fetch("stem_cr")
        assert should is True


class TestFetchFromCategory:

    async def test_persists_parsed_jobs(self, db_session):
        fake = FakeTelegram(
            messages_by_channel={"STEMJobsCR": [make_message(STEM_CR_1, 100)]}
        )
        orch = IngestOrchestrator(fake)
        jobs = await orch.fetch_from_category("stem_cr", db_session)

        assert len(jobs) == 1
        job = jobs[0]
        assert job.title == "DevOps & Platform Engineer"
        assert job.company == "GFT Group"
        assert job.category_id == "stem_cr"
        assert job.source_channel == "STEMJobsCR"
        assert job.source_message_id == 100
        assert job.dedup_hash
        assert job.expires_at > job.ingested_at

    async def test_duplicate_is_skipped(self, db_session):
        from app.parsing import compute_dedup_hash

        url = "https://jobs.gft.com/Costarica/job/Heredia-DevOps-&-Platform-Engineer-40101/1420528833"
        seed = make_job_posting(
            title="DevOps & Platform Engineer",
            company="GFT Group",
            url=url,
            dedup_hash=compute_dedup_hash(url, "DevOps & Platform Engineer", "GFT Group"),
        )
        db_session.add(seed)
        await db_session.commit()

        fake = FakeTelegram(
            messages_by_channel={"STEMJobsCR": [make_message(STEM_CR_1, 100)]}
        )
        orch = IngestOrchestrator(fake)
        jobs = await orch.fetch_from_category("stem_cr", db_session)

        assert len(jobs) == 1
        result = await db_session.execute(select(JobPosting))
        assert len(result.scalars().all()) == 1

    async def test_backup_group_used_when_primary_empty(self, db_session):
        fake = FakeTelegram(
            messages_by_channel={
                "STEMJobsCR": [],
                "STEMJobsLATAM": [make_message(STEM_LATAM_1, 200)],
            }
        )
        orch = IngestOrchestrator(fake)
        jobs = await orch.fetch_from_category("stem_cr", db_session)

        assert len(jobs) == 1
        assert jobs[0].source_channel == "STEMJobsLATAM"
        assert jobs[0].category_id == "stem_cr"

    async def test_unparseable_message_is_skipped(self, db_session):
        fake = FakeTelegram(
            messages_by_channel={"STEMJobsCR": [make_message("hi", 300)]}
        )
        orch = IngestOrchestrator(fake)
        jobs = await orch.fetch_from_category("stem_cr", db_session)

        assert jobs == []
        result = await db_session.execute(select(JobPosting))
        assert len(result.scalars().all()) == 0

    async def test_marks_group_down_after_max_failures(self, db_session):
        _reset_stem_cr()
        errors = {
            g["telegram_channel"]: ConnectionError("telegram unreachable")
            for g in GROUP_REGISTRY["stem_cr"]["groups"]
        }
        fake = FakeTelegram(errors=errors)
        orch = IngestOrchestrator(fake)

        for _ in range(3):
            await orch.fetch_from_category("stem_cr", db_session)

        primary = next(
            g for g in GROUP_REGISTRY["stem_cr"]["groups"]
            if g["id"] == "stem_cr_primary"
        )
        assert primary["status"] == "down"
        assert primary["consecutive_failures"] == 3

        result = await db_session.execute(
            select(GroupHealth).where(GroupHealth.group_id == "stem_cr_primary")
        )
        health = result.scalars().all()
        assert health
        assert health[-1].status == "down"


class TestRunIngest:

    async def test_run_ingest_skips_without_db_initialized(self, monkeypatch):
        import app.database as database

        monkeypatch.setattr(database, "async_session_maker", None)
        fake = FakeTelegram(
            messages_by_channel={"STEMJobsCR": [make_message(STEM_CR_1, 1)]}
        )
        orch = IngestOrchestrator(fake)
        await orch.run_ingest("job-1", "stem_cr")
        assert fake.calls == []

    async def test_run_ingest_completes_job(
        self, db_session, session_factory, monkeypatch
    ):
        import app.database as database

        monkeypatch.setattr(database, "async_session_maker", session_factory)
        _reset_stem_cr()

        fake = FakeTelegram(
            messages_by_channel={"STEMJobsCR": [make_message(STEM_CR_1, 1)]}
        )
        orch = IngestOrchestrator(fake)

        job = IngestJob(category_id="stem_cr")
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        await orch.run_ingest(job.id, "stem_cr")

        result = await db_session.execute(
            select(IngestJob).where(IngestJob.id == job.id)
        )
        done = result.scalar_one()
        await db_session.refresh(done)
        assert done.status == "done"
        assert done.result_count == 1

        result = await db_session.execute(select(JobPosting))
        assert len(result.scalars().all()) == 1