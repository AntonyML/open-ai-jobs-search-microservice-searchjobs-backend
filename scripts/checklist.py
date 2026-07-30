"""Startup checklist: verify DB, Telethon, parsing, and save."""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, text

logging.basicConfig(level=logging.WARNING)


async def run_checklist():
    from app.config import settings
    import app.database as db_mod
    from app.telegram import TelegramFetcher
    from app.parsing import parse_message, compute_dedup_hash
    from app.models import JobPosting

    # ── 1-3: DB connection & table creation ──
    print("=== 1-3: DB Connection & Table Creation ===")
    await db_mod.init_db(settings.database_url)
    print("  [OK] DB connected")

    maker = db_mod.async_session_maker
    assert maker is not None, "async_session_maker not set"

    async with maker() as db:
        table_count = await db.scalar(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'"))
        print(f"  Tables in DB: {table_count}")

        for t in ["ingested_jobs", "ingest_jobs", "group_health"]:
            exists = await db.scalar(
                text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=:t)"),
                {"t": t},
            )
            assert exists, f"Table {t} not created!"
            print(f"  [OK] {t} created")

        for t in ["users", "job_postings", "scrape_runs"]:
            exists = await db.scalar(
                text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=:t)"),
                {"t": t},
            )
            if exists:
                print(f"  [OK] {t} exists (untouched)")

    # ── 4: Telethon connect ──
    print("\n=== 4: Telethon Connection ===")
    tg = TelegramFetcher(
        settings.telegram_api_id,
        settings.telegram_api_hash,
        settings.telegram_session_dir,
    )
    await tg.start()
    print("  [OK] Telethon connected")

    # ── 5: Read 10 messages ──
    print("\n=== 5: Read 10 messages from STEMJobsLATAM ===")
    messages = await tg.get_messages("STEMJobsLATAM", limit=10)
    print(f"  [OK] Got {len(messages)} messages")
    for i, m in enumerate(messages):
        preview = (m.text or "")[:120].replace("\n", " | ")
        # strip non-Latin1 for Windows console
        safe = preview.encode("ascii", errors="replace").decode("ascii")
        print(f"  [{i+1}] {safe}")

    # ── 6: Parse ──
    print("\n=== 6: Parse messages ===")
    parsed_count = 0
    for i, m in enumerate(messages):
        result = parse_message(m.text or "", "freetext", "STEMJobsLATAM", m.id)
        if result:
            parsed_count += 1
            co = result.company or "?"
            loc = result.location or "?"
            print(f"  [OK][{i+1}] {result.title[:50]} | {co[:30]} | {loc[:20]}")
        else:
            print(f"  [FAIL][{i+1}] Could not parse")
    print(f"  Parsed: {parsed_count}/{len(messages)}")
    if parsed_count < 3:
        print("  [FAIL] Need at least 3 parsed jobs; parser needs fixing")

    # ── 7: Save to DB ──
    print("\n=== 7: Save to ingested_jobs ===")
    async with maker() as db:
        saved = 0
        for m in messages:
            result = parse_message(m.text or "", "freetext", "STEMJobsLATAM", m.id)
            if not result:
                continue
            dedup = compute_dedup_hash(result.company, result.title, result.location)
            now = datetime.now(timezone.utc)
            job = JobPosting(
                title=result.title,
                company=result.company,
                location=result.location,
                url=result.url,
                description=result.description,
                portal=result.portal,
                category_id="stem_cr",
                source_channel=result.source_channel,
                source_message_id=result.source_message_id,
                raw_text=result.raw_text,
                dedup_hash=dedup,
                ingested_at=now,
                expires_at=now + timedelta(hours=72),
            )
            db.add(job)
            saved += 1

        await db.commit()
        print(f"  [OK] {saved} jobs saved")

        result = await db.execute(select(JobPosting).limit(5))
        rows = result.scalars().all()
        for r in rows:
            print(f"    {r.title[:45]} | expires={r.expires_at.strftime('%m/%d %H:%M')}")

    await tg.stop()
    await db_mod.close_db()
    print("\n=== CHECKLIST COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(run_checklist())
