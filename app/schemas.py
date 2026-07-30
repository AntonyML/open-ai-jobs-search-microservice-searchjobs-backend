from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class IngestRequest(BaseModel):
    category_id: str
    keywords: Optional[str] = None


class IngestResponse(BaseModel):
    ingest_job_id: str
    status: str


class IngestStatusResponse(BaseModel):
    status: str
    result_count: Optional[int] = None
    error: Optional[str] = None


class JobResponse(BaseModel):
    id: str
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    salary: Optional[str] = None
    portal: Optional[str] = None
    category_id: str
    source_channel: str
    ingested_at: datetime
    expires_at: Optional[datetime] = None


class JobSearchResponse(BaseModel):
    jobs: list[JobResponse]
    count: int
    source: str
    ingest_job_id: Optional[str] = None
