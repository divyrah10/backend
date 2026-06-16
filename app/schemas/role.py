from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID


class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    permissions: List[str] = []


class RoleResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    permissions: List[str]

    class Config:
        from_attributes = True
