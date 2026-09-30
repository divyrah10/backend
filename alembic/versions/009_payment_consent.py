"""Record checkout payment consent

Revision ID: 009_payment_consent
Revises: 008_catalog_product_details
Create Date: 2026-09-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "009_payment_consent"
down_revision: Union[str, None] = "008_catalog_product_details"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("payment_consent_at", sa.DateTime(), nullable=True))
    op.add_column("orders", sa.Column("payment_consent_version", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "payment_consent_version")
    op.drop_column("orders", "payment_consent_at")
