"""Track stock per size

Revision ID: 010_size_stock
Revises: 009_payment_consent
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "010_size_stock"
down_revision: Union[str, None] = "009_payment_consent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Starts empty for every product: stock stays tracked as one total until an
    # admin enters per-size counts, so nothing sells out unexpectedly on deploy.
    op.add_column("products", sa.Column("size_stock", JSONB(), nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("products", "size_stock")
