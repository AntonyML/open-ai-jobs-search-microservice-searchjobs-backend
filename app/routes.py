from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_session
from app.models import JobPosting, IngestJob
from app.schemas import (
    IngestRequest,
    IngestResponse,
    IngestStatusResponse,
    JobResponse,
    JobSearchResponse,
)
from app.ingestion import IngestOrchestrator, infer_category

router = APIRouter()
_orchestrator: IngestOrchestrator | None = None


def setup_routes(o: IngestOrchestrator):
    global _orchestrator
    _orchestrator = o


def get_orch() -> IngestOrchestrator:
    assert _orchestrator is not None, "Orchestrator not initialized"
    return _orchestrator


@router.post("/ingest", response_model=IngestResponse)
async def trigger_ingest(
    req: IngestRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
):
    ingest_job = IngestJob(
        category_id=req.category_id,
        keywords=req.keywords,
    )
    db.add(ingest_job)
    await db.commit()
    await db.refresh(ingest_job)

    orch = get_orch()
    background_tasks.add_task(orch.run_ingest, ingest_job.id, req.category_id)

    return IngestResponse(
        ingest_job_id=ingest_job.id,
        status="queued",
    )


@router.get("/ingest/{job_id}/status", response_model=IngestStatusResponse)
async def get_ingest_status(
    job_id: str,
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(IngestJob).where(IngestJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Ingest job not found")
    return IngestStatusResponse(
        status=job.status,
        result_count=job.result_count,
        error=job.error,
    )


@router.get("/jobs/search", response_model=JobSearchResponse)
async def search_jobs(
    keywords: Optional[str] = None,
    location: Optional[str] = None,
    category_id: Optional[str] = None,
    db: AsyncSession = Depends(get_session),
):
    if not category_id:
        category_id = infer_category(keywords or "", location or "")

    now = datetime.now(timezone.utc)
    query = select(JobPosting).where(
        JobPosting.category_id == category_id,
        JobPosting.expires_at > now,
    )

    if keywords:
        kw = f"%{keywords}%"
        query = query.where(JobPosting.title.ilike(kw))

    query = query.order_by(JobPosting.ingested_at.desc()).limit(50)
    result = await db.execute(query)
    jobs = result.scalars().all()

    return JobSearchResponse(
        jobs=[
            JobResponse(
                id=j.id,
                title=j.title,
                company=j.company,
                location=j.location,
                url=j.url,
                description=j.description,
                salary=j.salary,
                portal=j.portal,
                category_id=j.category_id,
                source_channel=j.source_channel,
                ingested_at=j.ingested_at,
                expires_at=j.expires_at,
            )
            for j in jobs
        ],
        count=len(jobs),
        source="cache",
    )


@router.get("/health")
async def health():
    return {"status": "ok"}
