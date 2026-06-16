"""Switch to BetterAuth

Revision ID: 003_betterauth
Revises: 002
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '003_betterauth'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add auth_id column for BetterAuth user ID
    op.add_column('users', sa.Column('auth_id', sa.String(128), nullable=True))
    op.create_index('ix_users_auth_id', 'users', ['auth_id'], unique=True)

    # Drop hashed_password column
    op.drop_column('users', 'hashed_password')


def downgrade() -> None:
    # Add back hashed_password
    op.add_column('users', sa.Column('hashed_password', sa.String(255), nullable=True))

    # Remove auth_id
    op.drop_index('ix_users_auth_id', table_name='users')
    op.drop_column('users', 'auth_id')
