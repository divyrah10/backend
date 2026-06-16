from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from uuid import UUID
from decimal import Decimal
from datetime import datetime


class OrderItemCreate(BaseModel):
    product_id: UUID
    quantity: int
    attributes: Dict[str, Any] = {}


class OrderCreate(BaseModel):
    items: List[OrderItemCreate]
    shipping_address_id: UUID
    billing_address_id: Optional[UUID] = None
    customer_notes: Optional[str] = None
    idempotency_key: Optional[str] = None  # Frontend generates UUID to prevent double-submit


class OrderItemResponse(BaseModel):
    id: UUID
    product_id: UUID
    product_name: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal
    attributes: Dict[str, Any]

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: UUID
    order_number: str
    status: str
    subtotal: Decimal
    tax: Decimal
    shipping_cost: Decimal
    discount: Decimal
    total: Decimal
    shipping_address: Dict[str, Any]
    billing_address: Optional[Dict[str, Any]]
    customer_notes: Optional[str]
    items: List[OrderItemResponse]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    items: List[OrderResponse]
    total: int
    page: int
    page_size: int


class OrderStatusUpdate(BaseModel):
    status: str
    admin_notes: Optional[str] = None
