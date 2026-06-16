from enum import Enum
from typing import List, Set
from functools import wraps
from fastapi import HTTPException, status


class Permission(str, Enum):
    # User management
    MANAGE_USERS = "manage_users"
    MANAGE_ROLES = "manage_roles"

    # Product management
    MANAGE_PRODUCTS = "manage_products"
    MANAGE_CATEGORIES = "manage_categories"

    # Order management
    MANAGE_ALL_ORDERS = "manage_all_orders"
    MANAGE_OWN_ORDERS = "manage_own_orders"

    # Reviews
    APPROVE_REVIEWS = "approve_reviews"

    # Reports & Dashboard
    VIEW_REPORTS = "view_reports"
    VIEW_DASHBOARD = "view_dashboard"

    # Settings
    MANAGE_SETTINGS = "manage_settings"


class RoleName(str, Enum):
    SUPER_ADMIN = "super_admin"
    STORE_MANAGER = "store_manager"
    CUSTOMER_SERVICE = "customer_service"
    CUSTOMER = "customer"


# Role to permissions mapping
ROLE_PERMISSIONS: dict[RoleName, Set[Permission]] = {
    RoleName.SUPER_ADMIN: {
        Permission.MANAGE_USERS,
        Permission.MANAGE_ROLES,
        Permission.MANAGE_PRODUCTS,
        Permission.MANAGE_CATEGORIES,
        Permission.MANAGE_ALL_ORDERS,
        Permission.APPROVE_REVIEWS,
        Permission.VIEW_REPORTS,
        Permission.VIEW_DASHBOARD,
        Permission.MANAGE_SETTINGS,
    },
    RoleName.STORE_MANAGER: {
        Permission.MANAGE_USERS,
        Permission.MANAGE_PRODUCTS,
        Permission.MANAGE_CATEGORIES,
        Permission.MANAGE_ALL_ORDERS,
        Permission.APPROVE_REVIEWS,
        Permission.VIEW_REPORTS,
        Permission.VIEW_DASHBOARD,
    },
    RoleName.CUSTOMER_SERVICE: {
        Permission.MANAGE_ALL_ORDERS,
        Permission.APPROVE_REVIEWS,
        Permission.VIEW_DASHBOARD,
    },
    RoleName.CUSTOMER: {
        Permission.MANAGE_OWN_ORDERS,
    },
}


def get_role_permissions(role_name: str) -> Set[Permission]:
    try:
        role = RoleName(role_name)
        return ROLE_PERMISSIONS.get(role, set())
    except ValueError:
        return set()


def has_permission(user_permissions: Set[str], required_permission: Permission) -> bool:
    return required_permission.value in user_permissions


def require_permissions(*required_permissions: Permission):
    """Decorator to check if user has required permissions"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get current_user from kwargs (injected by dependency)
            current_user = kwargs.get('current_user')
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated"
                )

            user_permissions = get_role_permissions(current_user.role.name)

            for permission in required_permissions:
                if not has_permission({p.value for p in user_permissions}, permission):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Permission denied: {permission.value} required"
                    )

            return await func(*args, **kwargs)
        return wrapper
    return decorator
