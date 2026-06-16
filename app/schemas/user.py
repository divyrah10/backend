from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.schemas.role import RoleResponse


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    phone: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None
    role_id: Optional[UUID] = None


class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    phone: Optional[str]
    is_active: bool
    is_verified: bool
    role: RoleResponse
    created_at: datetime
    last_login: Optional[datetime]

    class Config:
        from_attributes = True


class UserProfileResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    phone: Optional[str]
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True
