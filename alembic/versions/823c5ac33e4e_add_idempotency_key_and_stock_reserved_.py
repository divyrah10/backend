"""Add idempotency_key and stock_reserved to orders

Revision ID: 823c5ac33e4e
Revises: 003_betterauth
Create Date: 2026-03-16 12:17:21.868756

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '823c5ac33e4e'
down_revision: Union[str, None] = '003_betterauth'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add idempotency_key and stock_reserved to orders table
    op.add_column('orders', sa.Column('idempotency_key', sa.String(length=100), nullable=True))
    op.add_column('orders', sa.Column('stock_reserved', sa.String(length=10), nullable=True))
    op.create_index(op.f('ix_orders_idempotency_key'), 'orders', ['idempotency_key'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_orders_idempotency_key'), table_name='orders')
    op.drop_column('orders', 'stock_reserved')
    op.drop_column('orders', 'idempotency_key')
