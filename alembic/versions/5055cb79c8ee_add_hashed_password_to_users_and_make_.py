"""Add hashed_password to users and make auth_id nullable

Revision ID: 5055cb79c8ee
Revises: 823c5ac33e4e
Create Date: 2026-03-16 12:41:12.717750

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5055cb79c8ee'
down_revision: Union[str, None] = '823c5ac33e4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add hashed_password column for admin users
    op.add_column('users', sa.Column('hashed_password', sa.String(length=255), nullable=True))

    # Make auth_id nullable (admin users won't have BetterAuth auth_id)
    op.alter_column('users', 'auth_id',
               existing_type=sa.VARCHAR(length=128),
               nullable=True)


def downgrade() -> None:
    op.drop_column('users', 'hashed_password')
    op.alter_column('users', 'auth_id',
               existing_type=sa.VARCHAR(length=128),
               nullable=False)
