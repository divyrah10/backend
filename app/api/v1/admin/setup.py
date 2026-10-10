"""
Admin Setup & Management API

This module handles:
1. First-time admin setup (when no admins exist)
2. Admin user management (invite, promote, demote)
3. Admin-specific authentication checks
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from app.db.session import get_db
from app.core.security import create_access_token, get_password_hash, verify_password
from app.core.permissions import RoleName, Permission, get_role_permissions
from app.api.deps import get_current_active_user, require_permission
from app.models.user import User
from app.models.role import Role
from app.schemas.user import UserResponse

router = APIRouter()


# ============================================================================
# Schemas
# ============================================================================

class SetupCheckResponse(BaseModel):
    needs_setup: bool
    message: str


class AdminSetupRequest(BaseModel):
    """First-time admin setup - creates the super admin"""
    email: EmailStr
    password: str
    full_name: str
    setup_key: str  # Secret key to prevent unauthorized setup


class AdminLoginRequest(BaseModel):
    """Admin login with email/password"""
    email: EmailStr
    password: str


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class InviteAdminRequest(BaseModel):
    """Invite a new admin user"""
    email: EmailStr
    full_name: str
    role: str = "store_manager"  # super_admin, store_manager, customer_service
    temporary_password: str = Field(min_length=12)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12)


class UpdateUserRoleRequest(BaseModel):
    """Update a user's role"""
    role: str


class AdminUserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    role_name: str
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime]

    class Config:
        from_attributes = True


# ============================================================================
# Setup Endpoints
# ============================================================================

@router.get("/check", response_model=SetupCheckResponse)
def check_setup_needed(db: Session = Depends(get_db)):
    """
    Check if initial admin setup is needed.
    Returns true if no admin users exist in the system.
    """
    # Check if any admin users exist
    admin_roles = db.query(Role).filter(
        Role.name.in_([RoleName.SUPER_ADMIN.value, RoleName.STORE_MANAGER.value])
    ).all()

    if not admin_roles:
        return SetupCheckResponse(
            needs_setup=True,
            message="Roles not found. Please run database migrations."
        )

    admin_role_ids = [r.id for r in admin_roles]
    admin_count = db.query(User).filter(
        User.role_id.in_(admin_role_ids),
        User.is_active == True
    ).count()

    if admin_count == 0:
        return SetupCheckResponse(
            needs_setup=True,
            message="No admin users found. Please complete initial setup."
        )

    return SetupCheckResponse(
        needs_setup=False,
        message="System is configured."
    )


@router.post("/initialize", response_model=AdminLoginResponse)
def initialize_admin(
    setup_data: AdminSetupRequest,
    db: Session = Depends(get_db)
):
    """
    First-time admin setup. Creates the initial super admin account.

    This endpoint only works when:
    1. No admin users exist in the system
    2. The correct setup_key is provided (from environment variable)

    The setup_key should be set in .env as ADMIN_SETUP_KEY
    """
    from app.core.config import settings

    # Verify setup key
    expected_key = getattr(settings, 'ADMIN_SETUP_KEY', 'notjustdark-setup-2024')
    if expected_key == 'notjustdark-setup-2024' or len(expected_key) < 24:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin setup is disabled until a secure ADMIN_SETUP_KEY is configured"
        )
    if setup_data.setup_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid setup key"
        )

    # Check if admin already exists
    super_admin_role = db.query(Role).filter(
        Role.name == RoleName.SUPER_ADMIN.value
    ).first()

    if not super_admin_role:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Super admin role not found. Please run database migrations."
        )

    existing_admin = db.query(User).filter(
        User.role_id == super_admin_role.id,
        User.is_active == True
    ).first()

    if existing_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin already exists. Use admin login instead."
        )

    # Check if email already used
    existing_email = db.query(User).filter(User.email == setup_data.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Create super admin user
    hashed_password = get_password_hash(setup_data.password)

    admin_user = User(
        auth_id=f"admin_{setup_data.email}",  # Internal auth ID for admin
        email=setup_data.email,
        full_name=setup_data.full_name,
        hashed_password=hashed_password,
        role_id=super_admin_role.id,
        is_active=True,
        is_verified=True,
        last_login=datetime.utcnow()
    )

    db.add(admin_user)
    db.commit()
    db.refresh(admin_user)

    # Create access token
    access_token = create_access_token(str(admin_user.id))

    return AdminLoginResponse(
        access_token=access_token,
        user=admin_user
    )


# ============================================================================
# Admin Login
# ============================================================================

@router.post("/login", response_model=AdminLoginResponse)
def admin_login(
    login_data: AdminLoginRequest,
    db: Session = Depends(get_db)
):
    """
    Admin-specific login endpoint.
    Only users with admin roles (super_admin, store_manager, customer_service) can login here.
    """
    # Find user by email
    user = db.query(User).filter(User.email == login_data.email).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # Check if user has admin role
    admin_roles = [RoleName.SUPER_ADMIN.value, RoleName.STORE_MANAGER.value, RoleName.CUSTOMER_SERVICE.value]
    if user.role.name not in admin_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin privileges required."
        )

    # Verify password
    if not hasattr(user, 'hashed_password') or not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin account not properly configured. Please contact super admin."
        )

    if not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated"
        )

    # Update last login
    user.last_login = datetime.utcnow()
    db.commit()

    # Create access token
    access_token = create_access_token(str(user.id))

    return AdminLoginResponse(
        access_token=access_token,
        user=user
    )


# ============================================================================
# Admin User Management
# ============================================================================

@router.get("/users", response_model=List[AdminUserResponse])
def list_admin_users(
    current_user: User = Depends(require_permission(Permission.MANAGE_USERS)),
    db: Session = Depends(get_db)
):
    """List all admin users (super_admin, store_manager, customer_service)"""
    admin_roles = db.query(Role).filter(
        Role.name.in_([
            RoleName.SUPER_ADMIN.value,
            RoleName.STORE_MANAGER.value,
            RoleName.CUSTOMER_SERVICE.value
        ])
    ).all()

    admin_role_ids = [r.id for r in admin_roles]

    users = db.query(User).filter(
        User.role_id.in_(admin_role_ids)
    ).all()

    return [
        AdminUserResponse(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role_name=u.role.name,
            is_active=u.is_active,
            created_at=u.created_at,
            last_login=u.last_login
        )
        for u in users
    ]


@router.post("/users/invite", response_model=AdminUserResponse)
def invite_admin_user(
    invite_data: InviteAdminRequest,
    current_user: User = Depends(require_permission(Permission.MANAGE_USERS)),
    db: Session = Depends(get_db)
):
    """
    Invite a new admin user.
    Only super_admin and store_manager can invite new admins.
    """
    # Validate role
    valid_roles = [RoleName.STORE_MANAGER.value, RoleName.CUSTOMER_SERVICE.value]

    # Only super_admin can create other super_admins
    if current_user.role.name == RoleName.SUPER_ADMIN.value:
        valid_roles.append(RoleName.SUPER_ADMIN.value)

    if invite_data.role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cannot assign role '{invite_data.role}'. Valid roles: {valid_roles}"
        )

    # Check if email already exists
    existing = db.query(User).filter(User.email == invite_data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Get role
    role = db.query(Role).filter(Role.name == invite_data.role).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Role '{invite_data.role}' not found"
        )

    # Create admin user
    hashed_password = get_password_hash(invite_data.temporary_password)

    new_admin = User(
        auth_id=f"admin_{invite_data.email}",
        email=invite_data.email,
        full_name=invite_data.full_name,
        hashed_password=hashed_password,
        role_id=role.id,
        is_active=True,
        is_verified=True
    )

    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)

    return AdminUserResponse(
        id=new_admin.id,
        email=new_admin.email,
        full_name=new_admin.full_name,
        role_name=new_admin.role.name,
        is_active=new_admin.is_active,
        created_at=new_admin.created_at,
        last_login=new_admin.last_login
    )


@router.put("/users/{user_id}/role", response_model=AdminUserResponse)
def update_user_role(
    user_id: UUID,
    role_data: UpdateUserRoleRequest,
    current_user: User = Depends(require_permission(Permission.MANAGE_USERS)),
    db: Session = Depends(get_db)
):
    """Update a user's role. Only super_admin can do this."""
    if current_user.role.name != RoleName.SUPER_ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admin can change user roles"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Can't change own role
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own role"
        )

    role = db.query(Role).filter(Role.name == role_data.role).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role '{role_data.role}' not found"
        )

    user.role_id = role.id
    db.commit()
    db.refresh(user)

    return AdminUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role_name=user.role.name,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login=user.last_login
    )


@router.put("/users/{user_id}/deactivate", response_model=AdminUserResponse)
def deactivate_user(
    user_id: UUID,
    current_user: User = Depends(require_permission(Permission.MANAGE_USERS)),
    db: Session = Depends(get_db)
):
    """Deactivate a user account."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Can't deactivate yourself
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account"
        )

    # Only super_admin can deactivate other admins
    admin_roles = [RoleName.SUPER_ADMIN.value, RoleName.STORE_MANAGER.value]
    if user.role.name in admin_roles and current_user.role.name != RoleName.SUPER_ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admin can deactivate admin accounts"
        )

    user.is_active = False
    db.commit()
    db.refresh(user)

    return AdminUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role_name=user.role.name,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login=user.last_login
    )


@router.put("/users/{user_id}/activate", response_model=AdminUserResponse)
def activate_user(
    user_id: UUID,
    current_user: User = Depends(require_permission(Permission.MANAGE_USERS)),
    db: Session = Depends(get_db)
):
    """Reactivate a deactivated user account."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = True
    db.commit()
    db.refresh(user)

    return AdminUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role_name=user.role.name,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login=user.last_login
    )


@router.put("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_own_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Replace the signed-in user's password, e.g. the temporary one from an invite."""
    if not current_user.hashed_password or not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    if data.new_password == data.current_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a different password")

    current_user.hashed_password = get_password_hash(data.new_password)
    db.commit()
