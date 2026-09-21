from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID


class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    permissions: List[str] = Field(default_factory=list)


class RoleResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    permissions: List[str]

    class Config:
        from_attributes = True
