"""Seed initial roles

Revision ID: 002
Revises: 001
Create Date: 2024-01-01

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLES = [
    {
        'id': str(uuid.uuid4()),
        'name': 'super_admin',
        'description': 'Full system access',
        'permissions': [
            'manage_users', 'manage_roles', 'manage_products', 'manage_categories',
            'manage_all_orders', 'approve_reviews', 'view_reports', 'view_dashboard',
            'manage_settings'
        ]
    },
    {
        'id': str(uuid.uuid4()),
        'name': 'store_manager',
        'description': 'Store management access',
        'permissions': [
            'manage_users', 'manage_products', 'manage_categories',
            'manage_all_orders', 'approve_reviews', 'view_reports', 'view_dashboard'
        ]
    },
    {
        'id': str(uuid.uuid4()),
        'name': 'customer_service',
        'description': 'Customer support access',
        'permissions': [
            'manage_all_orders', 'approve_reviews', 'view_dashboard'
        ]
    },
    {
        'id': str(uuid.uuid4()),
        'name': 'customer',
        'description': 'Regular customer',
        'permissions': [
            'manage_own_orders'
        ]
    }
]


def upgrade() -> None:
    roles_table = sa.table('roles',
        sa.column('id', postgresql.UUID),
        sa.column('name', sa.String),
        sa.column('description', sa.Text),
        sa.column('permissions', postgresql.JSONB)
    )

    for role in ROLES:
        op.execute(
            roles_table.insert().values(
                id=role['id'],
                name=role['name'],
                description=role['description'],
                permissions=role['permissions']
            )
        )


def downgrade() -> None:
    op.execute("DELETE FROM roles WHERE name IN ('super_admin', 'store_manager', 'customer_service', 'customer')")
