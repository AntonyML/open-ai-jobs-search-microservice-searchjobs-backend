"""API: contrato HTTP de ingesta, status y búsqueda (frontera realmente HTTP).

Usa api_client (httpx.ASGITransport + app real). El orquestador es un fake en
la frontera; la DB es SQLite en memoria vía session_factory.
"""

from datetime import datetime, timezone, timedelta

import pytest

from tests.factories import make_job_posting

pytestmark = pytest.mark.e2e


class TestIngest:

    async def test_post_ingest_queues_job(self, api_client):
        client, orch = api_client
        resp = await client.post("/api/v1/ingest", json={"category_id": "stem_cr"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert data["ingest_job_id"]
        assert orch.calls and orch.calls[0][1] == "stem_cr"

    async def test_post_ingest_requires_category_id(self, api_client):
        client, _ = api_client
        resp = await client.post("/api/v1/ingest", json={})
        assert resp.status_code == 422

    async def test_ingest_status_is_reported(self, api_client):
        client, _ = api_client
        created = await client.post(
            "/api/v1/ingest", json={"category_id": "latam_remote"}
        )
        job_id = created.json()["ingest_job_id"]

        resp = await client.get(f"/api/v1/ingest/{job_id}/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "done"
        assert resp.json()["result_count"] == 0

    async def test_ingest_status_404(self, api_client):
        client, _ = api_client
        resp = await client.get("/api/v1/ingest/does-not-exist/status")
        assert resp.status_code == 404


class TestSearch:

    async def test_search_returns_jobs(self, api_client, session_factory):
        client, _ = api_client
        job = make_job_posting(
            title="DevOps & Platform Engineer",
            company="GFT Group",
            category_id="stem_cr",
            source_channel="STEMJobsCR",
        )
        async with session_factory() as db:
            db.add(job)
            await db.commit()

        resp = await client.get(
            "/api/v1/jobs/search",
            params={"keywords": "DevOps", "category_id": "stem_cr"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["source"] == "cache"
        assert data["jobs"][0]["title"] == "DevOps & Platform Engineer"
        assert data["jobs"][0]["company"] == "GFT Group"
        assert data["jobs"][0]["category_id"] == "stem_cr"
        assert data["jobs"][0]["source_channel"] == "STEMJobsCR"

    async def test_search_excludes_expired(self, api_client, session_factory):
        client, _ = api_client
        now = datetime.now(timezone.utc)
        expired = make_job_posting(
            title="Expired Job",
            ingested_at=now - timedelta(hours=100),
            expires_at=now - timedelta(hours=1),
        )
        async with session_factory() as db:
            db.add(expired)
            await db.commit()

        resp = await client.get(
            "/api/v1/jobs/search", params={"category_id": "stem_cr"}
        )
        assert resp.json()["count"] == 0

    async def test_search_orders_newest_first(self, api_client, session_factory):
        client, _ = api_client
        now = datetime.now(timezone.utc)
        older = make_job_posting(title="Older Job", ingested_at=now - timedelta(hours=2))
        newer = make_job_posting(title="Newer Job", ingested_at=now)
        async with session_factory() as db:
            db.add_all([older, newer])
            await db.commit()

        resp = await client.get(
            "/api/v1/jobs/search", params={"category_id": "stem_cr"}
        )
        titles = [j["title"] for j in resp.json()["jobs"]]
        assert titles == ["Newer Job", "Older Job"]

    async def test_search_keywords_filter_title(self, api_client, session_factory):
        client, _ = api_client
        now = datetime.now(timezone.utc)
        match = make_job_posting(title="Backend Engineer", ingested_at=now)
        other = make_job_posting(title="Marketing Manager", ingested_at=now)
        async with session_factory() as db:
            db.add_all([match, other])
            await db.commit()

        resp = await client.get(
            "/api/v1/jobs/search",
            params={"keywords": "Engineer", "category_id": "stem_cr"},
        )
        titles = [j["title"] for j in resp.json()["jobs"]]
        assert titles == ["Backend Engineer"]

    async def test_search_infers_category_from_location(self, api_client, session_factory):
        client, _ = api_client
        job = make_job_posting(
            title="Developer Role",
            location="Heredia, CR",
            category_id="stem_cr",
        )
        async with session_factory() as db:
            db.add(job)
            await db.commit()

        resp = await client.get("/api/v1/jobs/search", params={"location": "Heredia"})
        assert resp.status_code == 200
        assert resp.json()["count"] == 1


class TestHealth:

    async def test_health(self, api_client):
        client, _ = api_client
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}