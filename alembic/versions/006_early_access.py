"""Add early-access attribution and leads

Revision ID: 006_early_access
Revises: 5055cb79c8ee
Create Date: 2026-09-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "006_early_access"
down_revision: Union[str, None] = "5055cb79c8ee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "early_access_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("medium", sa.String(length=100), nullable=False),
        sa.Column("campaign", sa.String(length=100), nullable=False),
        sa.Column("content", sa.String(length=100), nullable=True),
        sa.Column("landing_path", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "event_type", name="uq_early_access_session_event"),
    )
    op.create_index("ix_early_access_events_session_id", "early_access_events", ["session_id"])
    op.create_index("ix_early_access_events_event_type", "early_access_events", ["event_type"])
    op.create_index("ix_early_access_events_source", "early_access_events", ["source"])
    op.create_index("ix_early_access_events_campaign", "early_access_events", ["campaign"])
    op.create_index("ix_early_access_events_content", "early_access_events", ["content"])

    op.create_table(
        "early_access_leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("medium", sa.String(length=100), nullable=False),
        sa.Column("campaign", sa.String(length=100), nullable=False),
        sa.Column("content", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_early_access_leads_email", "early_access_leads", ["email"], unique=True)
    op.create_index("ix_early_access_leads_session_id", "early_access_leads", ["session_id"])
    op.create_index("ix_early_access_leads_source", "early_access_leads", ["source"])
    op.create_index("ix_early_access_leads_campaign", "early_access_leads", ["campaign"])
    op.create_index("ix_early_access_leads_content", "early_access_leads", ["content"])


def downgrade() -> None:
    op.drop_table("early_access_leads")
    op.drop_table("early_access_events")
