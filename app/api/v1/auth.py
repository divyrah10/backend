from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from app.db.session import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.core.permissions import RoleName
from app.models.user import User
from app.models.role import Role
from app.schemas.user import UserCreate, UserResponse
from app.schemas.auth import Token
from app.api.deps import get_current_active_user

router = APIRouter()


# ============================================================================
# Registration
# ============================================================================

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new customer account.

    Stores a bcrypt hash of the password (never the plaintext) and assigns the
    default ``customer`` role. Use ``POST /auth/login`` afterwards to obtain tokens.
    """
    # Reject duplicate emails (the column is unique, but give a clean 400)
    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists.",
        )

    customer_role = db.query(Role).filter(Role.name == RoleName.CUSTOMER.value).first()
    if not customer_role:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Customer role not found. Please run database migrations.",
        )

    user = User(
        email=user_data.email,
        full_name=user_data.full_name,
        phone=user_data.phone,
        hashed_password=get_password_hash(user_data.password),
        role_id=customer_role.id,
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ============================================================================
# Login (OAuth2 password flow — form fields: username, password)
# ============================================================================

@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Authenticate with email + password and receive access & refresh tokens.

    The OAuth2 form uses ``username`` for the email field. Errors are kept
    deliberately generic so we don't reveal whether an email is registered.
    """
    user = db.query(User).filter(User.email == form_data.username).first()

    if not user or not user.hashed_password or not verify_password(
        form_data.password, user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    user.last_login = datetime.utcnow()
    db.commit()

    return Token(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


# ============================================================================
# Refresh — exchange a valid refresh token for a new token pair
# ============================================================================

@router.post("/refresh", response_model=Token)
def refresh_token(refresh_token: str, db: Session = Depends(get_db)):
    """Issue a new access/refresh pair from a valid refresh token."""
    payload = decode_token(refresh_token, expected_type="refresh")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer active",
        )

    return Token(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


# ============================================================================
# Current user
# ============================================================================

@router.get("/me", response_model=UserResponse)
def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """Get the currently authenticated user."""
    return current_user


@router.put("/me", response_model=UserResponse)
def update_current_user(
    full_name: Optional[str] = None,
    phone: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update the current user's profile."""
    if full_name:
        current_user.full_name = full_name
    if phone:
        current_user.phone = phone
    db.commit()
    db.refresh(current_user)
    return current_user
