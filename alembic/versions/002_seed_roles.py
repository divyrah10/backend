"""Seed initial roles

Revision ID: 002
Revises: 001
Create Date: 2024-01-01

"""
from typing import Sequence, Union
from alembic import op
import uuid
import json

revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLES = [
    {
        'id': str(uuid.uuid5(uuid.NAMESPACE_URL, 'notjustdark:role:super_admin')),
        'name': 'super_admin',
        'description': 'Full system access',
        'permissions': [
            'manage_users', 'manage_roles', 'manage_products', 'manage_categories',
            'manage_all_orders', 'approve_reviews', 'view_reports', 'view_dashboard',
            'manage_settings'
        ]
    },
    {
        'id': str(uuid.uuid5(uuid.NAMESPACE_URL, 'notjustdark:role:store_manager')),
        'name': 'store_manager',
        'description': 'Store management access',
        'permissions': [
            'manage_users', 'manage_products', 'manage_categories',
            'manage_all_orders', 'approve_reviews', 'view_reports', 'view_dashboard'
        ]
    },
    {
        'id': str(uuid.uuid5(uuid.NAMESPACE_URL, 'notjustdark:role:customer_service')),
        'name': 'customer_service',
        'description': 'Customer support access',
        'permissions': [
            'manage_all_orders', 'approve_reviews', 'view_dashboard'
        ]
    },
    {
        'id': str(uuid.uuid5(uuid.NAMESPACE_URL, 'notjustdark:role:customer')),
        'name': 'customer',
        'description': 'Regular customer',
        'permissions': [
            'manage_own_orders'
        ]
    }
]


def upgrade() -> None:
    for role in ROLES:
        permissions = json.dumps(role['permissions']).replace("'", "''")
        op.execute(
            "INSERT INTO roles (id, name, description, permissions) "
            f"VALUES ('{role['id']}'::uuid, '{role['name']}', "
            f"'{role['description']}', '{permissions}'::jsonb)"
        )


def downgrade() -> None:
    op.execute("DELETE FROM roles WHERE name IN ('super_admin', 'store_manager', 'customer_service', 'customer')")
