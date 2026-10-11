from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from app.schemas.category import CategoryResponse


class ProductCreate(BaseModel):
    name: str
    slug: Optional[str] = None
    description: Optional[str] = None
    short_description: Optional[str] = None
    price: Decimal
    compare_at_price: Optional[Decimal] = None
    sku: Optional[str] = None
    stock_quantity: int = 0
    low_stock_threshold: int = 5
    category_id: Optional[UUID] = None
    vendor_id: Optional[UUID] = None
    images: List[str] = Field(default_factory=list)
    attributes: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    is_featured: bool = False
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    short_description: Optional[str] = None
    price: Optional[Decimal] = None
    compare_at_price: Optional[Decimal] = None
    sku: Optional[str] = None
    stock_quantity: Optional[int] = None
    low_stock_threshold: Optional[int] = None
    category_id: Optional[UUID] = None
    vendor_id: Optional[UUID] = None
    images: Optional[List[str]] = None
    attributes: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    is_featured: Optional[bool] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None


class ProductResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    description: Optional[str]
    short_description: Optional[str]
    price: Decimal
    compare_at_price: Optional[Decimal]
    sku: Optional[str]
    stock_quantity: int
    size_stock: Dict[str, int] = {}
    category: Optional[CategoryResponse]
    images: List[str]
    attributes: Dict[str, Any]
    is_active: bool
    is_featured: bool
    is_on_sale: bool
    discount_percentage: int
    in_stock: bool
    created_at: datetime
    average_rating: Optional[float] = None
    review_count: int = 0

    class Config:
        from_attributes = True


class ProductListResponse(BaseModel):
    items: List[ProductResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
