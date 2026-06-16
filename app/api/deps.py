from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import decode_token
from app.core.permissions import Permission, get_role_permissions
from app.models.user import User

security = HTTPBearer(auto_error=False)


def get_current_user(
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[User]:
    """Get current user from JWT token"""
    if not credentials:
        return None

    token = credentials.credentials
    payload = decode_token(token, expected_type="access")
    if not payload:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        return None

    return user


def get_current_active_user(
    current_user: Optional[User] = Depends(get_current_user)
) -> User:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    return current_user


def require_permission(*permissions: Permission):
    """Dependency to check if user has required permissions"""
    def permission_checker(current_user: User = Depends(get_current_active_user)) -> User:
        user_permissions = get_role_permissions(current_user.role.name)
        user_permission_values = {p.value for p in user_permissions}

        for permission in permissions:
            if permission.value not in user_permission_values:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {permission.value} required"
                )
        return current_user

    return permission_checker


def get_session_id(session_id: Optional[str] = None) -> Optional[str]:
    """Get session ID for guest cart/compare functionality"""
    return session_id
