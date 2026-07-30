import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Text, DateTime
from app.database import Base


class JobPosting(Base):
    __tablename__ = "ingested_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(300), nullable=False, index=True)
    company = Column(String(200), nullable=True)
    location = Column(String(200), nullable=True)
    url = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    salary = Column(String(100), nullable=True)
    portal = Column(String(50), nullable=True)
    category_id = Column(String(50), nullable=False, index=True)
    source_channel = Column(String(100), nullable=False)
    source_message_id = Column(Integer, nullable=False)
    raw_text = Column(Text, nullable=False)
    ingested_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    expires_at = Column(DateTime(timezone=True), index=True)
    dedup_hash = Column(String(64), unique=True, index=True)


class IngestJob(Base):
    __tablename__ = "ingest_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    category_id = Column(String(50), nullable=False)
    keywords = Column(String(300), nullable=True)
    status = Column(String(20), default="queued")
    result_count = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)


class GroupHealth(Base):
    __tablename__ = "group_health"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(50), index=True)
    status = Column(String(20))
    consecutive_failures = Column(Integer, default=0)
    failure_reason = Column(Text, nullable=True)
    last_success = Column(DateTime(timezone=True), nullable=True)
    checked_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
