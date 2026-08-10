"""Schemas Pydantic: validación de request/response del API."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas import (
    IngestRequest,
    IngestResponse,
    IngestStatusResponse,
    JobResponse,
    JobSearchResponse,
)

pytestmark = pytest.mark.unit


class TestIngestRequest:

    def test_requires_category_id(self):
        with pytest.raises(ValidationError):
            IngestRequest()

    def test_keywords_optional(self):
        req = IngestRequest(category_id="stem_cr")
        assert req.category_id == "stem_cr"
        assert req.keywords is None

    def test_accepts_keywords(self):
        req = IngestRequest(category_id="stem_cr", keywords="devops")
        assert req.keywords == "devops"


class TestIngestResponse:

    def test_fields(self):
        resp = IngestResponse(ingest_job_id="abc-123", status="queued")
        assert resp.ingest_job_id == "abc-123"
        assert resp.status == "queued"


class TestIngestStatusResponse:

    def test_defaults(self):
        resp = IngestStatusResponse(status="done")
        assert resp.result_count is None
        assert resp.error is None

    def test_full(self):
        resp = IngestStatusResponse(status="failed", result_count=2, error="boom")
        assert resp.result_count == 2
        assert resp.error == "boom"


class TestJobResponse:

    def test_requires_source_fields(self):
        with pytest.raises(ValidationError):
            JobResponse(id="1", title="T", category_id="stem_cr")

    def test_valid_job_roundtrip(self):
        now = datetime.now(timezone.utc)
        job = JobResponse(
            id="abc",
            title="Engineer",
            company="ACME",
            category_id="stem_cr",
            source_channel="STEMJobsCR",
            ingested_at=now,
        )
        assert job.id == "abc"
        assert job.company == "ACME"
        assert job.url is None
        assert job.salary is None
        assert job.expires_at is None


class TestJobSearchResponse:

    def test_defaults(self):
        resp = JobSearchResponse(jobs=[], count=0, source="cache")
        assert resp.ingest_job_id is None
        assert resp.jobs == []