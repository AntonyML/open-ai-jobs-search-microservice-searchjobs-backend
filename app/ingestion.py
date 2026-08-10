import structlog
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.registry import GROUP_REGISTRY
from app.parsing import parse_message, compute_dedup_hash
from app.models import JobPosting, IngestJob, GroupHealth
from app.telegram import TelegramFetcher
from app.alert import send_admin_alert

logger = structlog.get_logger(__name__)

MAX_CONSECUTIVE_FAILURES = 3
DEMAND_TIERS = [
    (0, 5, 24),
    (5, 20, 12),
    (20, 50, 6),
    (50, 999, 3),
]


def get_poll_interval(demand_score: int, category_id: str) -> int:
    # Check if category has a custom interval
    cat = GROUP_REGISTRY.get(category_id)
    if cat and "poll_interval_hours" in cat:
        return cat["poll_interval_hours"]
    for low, high, interval in DEMAND_TIERS:
        if low <= demand_score < high:
            return interval
    return 24


def infer_category(keywords: str, location: str) -> str:
    kw_lower = keywords.lower()
    loc_lower = location.lower().strip()
    for cat_id, cat in GROUP_REGISTRY.items():
        if any(k in kw_lower for k in cat.get("search_keywords", [])):
            return cat_id
        if loc_lower and any(k in loc_lower for k in cat.get("search_keywords", [])):
            return cat_id
    return "stem_cr"


class IngestOrchestrator:
    def __init__(self, telegram: TelegramFetcher):
        self.telegram = telegram

    def should_fetch(self, category_id: str) -> tuple[bool, dict]:
        cat = GROUP_REGISTRY.get(category_id)
        if not cat:
            return False, {}
        cat["demand_score"] = cat.get("demand_score", 0) + 1
        interval = get_poll_interval(cat["demand_score"], category_id)
        cat["poll_interval_hours"] = interval
        last = cat.get("last_polled")
        if last is None:
            return True, cat
        elapsed = (datetime.now(timezone.utc) - last).total_seconds() / 3600
        return elapsed >= interval, cat

    async def fetch_from_category(
        self, category_id: str, db: AsyncSession, limit: int = 50
    ) -> list[JobPosting]:
        cat = GROUP_REGISTRY.get(category_id)
        if not cat:
            logger.warning("unknown_category", category_id=category_id)
            return []

        groups = sorted(cat["groups"], key=lambda g: g.get("priority", 99))
        log = logger.bind(category_id=category_id, category_label=cat["label"])
        log.info("ingest_start", group_count=len(groups))

        total_parsed = 0
        total_skipped_dedup = 0
        total_failed = 0
        failure_details = []

        for group in groups:
            if group.get("status") == "down":
                log.info("group_skipped_down", group_id=group["id"])
                continue

            try:
                messages = await self.telegram.get_messages(
                    group["telegram_channel"], limit=limit
                )
            except Exception as e:
                group["consecutive_failures"] = group.get("consecutive_failures", 0) + 1
                fail_count = group["consecutive_failures"]
                log.error(
                    "group_fetch_failed",
                    group_id=group["id"],
                    channel=group["telegram_channel"],
                    consecutive_failures=fail_count,
                    max_failures=MAX_CONSECUTIVE_FAILURES,
                    error=str(e),
                )
                failure_details.append({
                    "group_id": group["id"],
                    "reason": str(e),
                    "channel": group["telegram_channel"],
                })
                if fail_count >= MAX_CONSECUTIVE_FAILURES:
                    group["status"] = "down"
                    log.warning(
                        "group_marked_down",
                        group_id=group["id"],
                        channel=group["telegram_channel"],
                    )
                    db.add(GroupHealth(
                        group_id=group["id"],
                        status="down",
                        consecutive_failures=fail_count,
                        failure_reason=str(e),
                    ))
                    await db.commit()
                continue

            group["status"] = "active"
            group["consecutive_failures"] = 0
            group["last_success"] = datetime.now(timezone.utc)

            db.add(GroupHealth(
                group_id=group["id"],
                status="active",
                consecutive_failures=0,
                last_success=datetime.now(timezone.utc),
            ))

            group_log = log.bind(
                group_id=group["id"],
                channel=group["telegram_channel"],
                format_template=group.get("format_template", "freetext"),
            )
            group_log.info("group_fetch_success", messages_fetched=len(messages))

            parsed_count = 0
            dedup_skipped = 0
            failed_count = 0

            for msg in messages:
                parsed = parse_message(
                    text=msg.text or "",
                    format_template=group.get("format_template", "freetext"),
                    channel=group["telegram_channel"],
                    msg_id=msg.id,
                )
                if not parsed:
                    failed_count += 1
                    group_log.debug(
                        "parse_failed",
                        msg_id=msg.id,
                        reason="parser returned None",
                        preview=(msg.text or "")[:100],
                    )
                    continue

                dedup_hash = compute_dedup_hash(
                    parsed.url, parsed.title, parsed.company
                )
                existing = await db.execute(
                    select(JobPosting).where(JobPosting.dedup_hash == dedup_hash)
                )
                if existing.scalar_one_or_none():
                    dedup_skipped += 1
                    continue

                now = datetime.now(timezone.utc)
                job = JobPosting(
                    title=parsed.title,
                    company=parsed.company,
                    location=parsed.location,
                    url=parsed.url,
                    description=parsed.description,
                    salary=parsed.salary,
                    portal=parsed.portal,
                    category_id=category_id,
                    source_channel=parsed.source_channel,
                    source_message_id=parsed.source_message_id,
                    raw_text=parsed.raw_text,
                    dedup_hash=dedup_hash,
                    ingested_at=now,
                    expires_at=now + timedelta(hours=72),
                )
                db.add(job)
                parsed_count += 1

            await db.commit()
            cat["last_polled"] = datetime.now(timezone.utc)

            total_parsed += parsed_count
            total_skipped_dedup += dedup_skipped
            total_failed += failed_count

            group_log.info(
                "group_ingest_complete",
                jobs_parsed=parsed_count,
                jobs_skipped_dedup=dedup_skipped,
                jobs_failed_parse=failed_count,
            )

            # Return after first successful group in the category
            all_jobs = await self._get_recent_jobs(db, category_id)
            if all_jobs:
                log.info(
                    "ingest_complete",
                    total_jobs=len(all_jobs),
                    total_parsed=total_parsed,
                    total_skipped_dedup=total_skipped_dedup,
                    total_failed_parse=total_failed,
                    primary_group=group["id"],
                )
                return all_jobs

        # All groups failed — log and alert
        log.error(
            "all_groups_failed",
            total_parsed=total_parsed,
            total_skipped_dedup=total_skipped_dedup,
            total_failed_parse=total_failed,
            failure_details=failure_details,
        )

        admin_email = cat.get("admin_alert_email", "")
        if admin_email:
            from app.config import settings
            await send_admin_alert(
                email=admin_email,
                subject=f"All groups down for '{cat['label']}'",
                body=(
                    f"Category: {cat['label']}\n"
                    f"All groups failed during ingest.\n"
                    f"Failures: {failure_details}\n"
                    f"Time: {datetime.now(timezone.utc).isoformat()}"
                ),
                resend_api_key=settings.resend_api_key,
                resend_from_email=settings.resend_from_email,
            )
        return []

    async def _get_recent_jobs(
        self, db: AsyncSession, category_id: str, limit: int = 50
    ) -> list[JobPosting]:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(JobPosting)
            .where(
                JobPosting.category_id == category_id,
                JobPosting.expires_at > now,
            )
            .order_by(JobPosting.ingested_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def run_ingest(self, ingest_job_id: str, category_id: str):
        from app.database import async_session_maker

        log = logger.bind(ingest_job_id=ingest_job_id, category_id=category_id)

        maker = async_session_maker
        if not maker:
            log.error("database_not_initialized")
            return

        async with maker() as db:
            should, cat = self.should_fetch(category_id)
            if not should:
                log.info(
                    "category_still_fresh_skipping",
                    category_label=cat.get("label", category_id),
                )
                jobs = await self._get_recent_jobs(db, category_id)
                await self._complete_job(db, ingest_job_id, len(jobs))
                return

            try:
                log.info(
                    "starting_ingest",
                    category_label=cat.get("label", category_id),
                )
                jobs = await self.fetch_from_category(category_id, db)
                await self._complete_job(db, ingest_job_id, len(jobs))
                log.info(
                    "ingest_finished",
                    total_jobs=len(jobs),
                )
            except Exception as e:
                log.exception("ingest_failed", error=str(e))
                await self._fail_job(db, ingest_job_id, str(e))

    async def _complete_job(self, db: AsyncSession, job_id: str, count: int):
        result = await db.execute(
            select(IngestJob).where(IngestJob.id == job_id)
        )
        job = result.scalar_one_or_none()
        if job:
            job.status = "done"
            job.result_count = count
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()

    async def _fail_job(self, db: AsyncSession, job_id: str, error: str):
        result = await db.execute(
            select(IngestJob).where(IngestJob.id == job_id)
        )
        job = result.scalar_one_or_none()
        if job:
            job.status = "failed"
            job.error = error
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
