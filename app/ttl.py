import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import delete
from app.models import JobPosting

logger = logging.getLogger(__name__)


async def clean_expired_jobs(db, ttl_hours: int):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
    result = await db.execute(
        delete(JobPosting).where(JobPosting.ingested_at < cutoff)
    )
    await db.commit()
    if result.rowcount:
        logger.info(
            "TTL Cleaner: %d jobs removed (cutoff=%s)",
            result.rowcount, cutoff.isoformat(),
        )
