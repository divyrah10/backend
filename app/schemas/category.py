from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID


class CategoryCreate(BaseModel):
    name: str
    slug: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    parent_id: Optional[UUID] = None
    sort_order: int = 0
    is_active: bool = True


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    parent_id: Optional[UUID] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class CategoryResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    description: Optional[str]
    image_url: Optional[str]
    parent_id: Optional[UUID]
    sort_order: int
    is_active: bool

    class Config:
        from_attributes = True


class CategoryWithChildren(CategoryResponse):
    subcategories: List["CategoryWithChildren"] = Field(default_factory=list)


CategoryWithChildren.model_rebuild()
