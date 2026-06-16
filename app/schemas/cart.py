from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from uuid import UUID
from decimal import Decimal


class CartItemCreate(BaseModel):
    product_id: UUID
    quantity: int = 1
    attributes: Dict[str, Any] = {}


class CartItemUpdate(BaseModel):
    quantity: int


class CartItemResponse(BaseModel):
    id: UUID
    product_id: UUID
    product_name: str
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
