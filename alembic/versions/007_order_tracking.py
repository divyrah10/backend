"""Add provider-neutral per-order shipment tracking

Revision ID: 007_order_tracking
Revises: 006_early_access
Create Date: 2026-09-26
"""

from datetime import datetime
import secrets
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "007_order_tracking"
down_revision: Union[str, None] = "006_early_access"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shipments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tracking_token", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("provider_shipment_id", sa.String(length=100), nullable=True),
        sa.Column("awb_code", sa.String(length=100), nullable=True),
        sa.Column("courier_name", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("tracking_url", sa.String(length=500), nullable=True),
        sa.Column("estimated_delivery", sa.DateTime(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id"),
        sa.UniqueConstraint("tracking_token"),
    )
    op.create_index("ix_shipments_order_id", "shipments", ["order_id"])
    op.create_index("ix_shipments_tracking_token", "shipments", ["tracking_token"])
    op.create_index("ix_shipments_provider_shipment_id", "shipments", ["provider_shipment_id"])
    op.create_index("ix_shipments_awb_code", "shipments", ["awb_code"])
    op.create_index("ix_shipments_status", "shipments", ["status"])

    op.create_table(
        "tracking_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shipment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tracking_events_shipment_id", "tracking_events", ["shipment_id"])
    op.create_index("ix_tracking_events_status", "tracking_events", ["status"])

    # Existing orders receive private tracking links and an initial event too.
    connection = op.get_bind()
    orders = connection.execute(sa.text("SELECT id, created_at FROM orders")).fetchall()
    now = datetime.utcnow()
    for order in orders:
        shipment_id = uuid.uuid4()
        occurred_at = order.created_at or now
        connection.execute(
            sa.text(
                """
                INSERT INTO shipments
                    (id, order_id, tracking_token, provider, status, created_at, updated_at)
                VALUES
                    (:id, :order_id, :tracking_token, 'shiprocket', 'order_confirmed', :created_at, :updated_at)
                """
            ),
            {
                "id": shipment_id,
                "order_id": order.id,
                "tracking_token": secrets.token_urlsafe(32),
                "created_at": occurred_at,
                "updated_at": now,
            },
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO tracking_events
                    (id, shipment_id, status, title, description, occurred_at, created_at, updated_at)
                VALUES
                    (:id, :shipment_id, 'order_confirmed', 'Order confirmed',
                     'We received your order and are preparing it for dispatch.',
                     :occurred_at, :created_at, :updated_at)
                """
            ),
            {
                "id": uuid.uuid4(),
                "shipment_id": shipment_id,
                "occurred_at": occurred_at,
                "created_at": now,
                "updated_at": now,
            },
        )


def downgrade() -> None:
    op.drop_table("tracking_events")
    op.drop_table("shipments")
