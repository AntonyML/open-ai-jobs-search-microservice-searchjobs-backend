"""Initial tables for ingesta microservice.

Revision ID: 001
Revises:
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingested_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False, index=True),
        sa.Column("company", sa.String(200), nullable=True),
        sa.Column("location", sa.String(200), nullable=True),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("salary", sa.String(100), nullable=True),
        sa.Column("portal", sa.String(50), nullable=True),
        sa.Column("category_id", sa.String(50), nullable=False, index=True),
        sa.Column("source_channel", sa.String(100), nullable=False),
        sa.Column("source_message_id", sa.Integer, nullable=False),
        sa.Column("raw_text", sa.Text, nullable=False),
        sa.Column("dedup_hash", sa.String(64), unique=True, index=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            index=True,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            index=True,
        ),
    )

    op.create_table(
        "ingest_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("category_id", sa.String(50), nullable=False, index=True),
        sa.Column("keywords", sa.String(300), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            server_default="queued",
            index=True,
        ),
        sa.Column("result_count", sa.Integer, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "group_health",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.String(50), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("consecutive_failures", sa.Integer, nullable=True),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column("last_success", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("group_health")
    op.drop_table("ingest_jobs")
    op.drop_table("ingested_jobs")
