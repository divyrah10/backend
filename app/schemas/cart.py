from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from uuid import UUID
from decimal import Decimal


class CartItemCreate(BaseModel):
    product_id: UUID
    quantity: int = Field(default=1, ge=1)
    attributes: Dict[str, Any] = Field(default_factory=dict)


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=0)


class CartItemResponse(BaseModel):
    id: UUID
    product_id: UUID
    product_name: str
    product_slug: str
    product_sku: Optional[str] = None
    product_image: Optional[str]
    product_price: Decimal
    quantity: int
    attributes: Dict[str, Any]
    subtotal: Decimal

    class Config:
        from_attributes = True


class CartResponse(BaseModel):
    items: List[CartItemResponse]
    total_items: int
    subtotal: Decimal
    tax: Decimal
    total: Decimal
