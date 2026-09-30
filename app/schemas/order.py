from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from uuid import UUID
from decimal import Decimal
from datetime import datetime


class OrderItemCreate(BaseModel):
    product_id: UUID
    quantity: int = Field(ge=1)
    attributes: Dict[str, Any] = Field(default_factory=dict)


class OrderCreate(BaseModel):
    items: List[OrderItemCreate] = Field(min_length=1)
    shipping_address_id: UUID
    billing_address_id: Optional[UUID] = None
    customer_notes: Optional[str] = None
    idempotency_key: Optional[str] = None  # Frontend generates UUID to prevent double-submit
    payment_consent: bool = False
    payment_consent_version: Optional[str] = Field(default=None, max_length=50)


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


class TrackingEventResponse(BaseModel):
    id: UUID
    status: str
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    occurred_at: datetime

    class Config:
        from_attributes = True


class ShipmentResponse(BaseModel):
    id: UUID
    tracking_token: str
    provider: str
    provider_shipment_id: Optional[str] = None
    awb_code: Optional[str] = None
    courier_name: Optional[str] = None
    status: str
    tracking_url: Optional[str] = None
    estimated_delivery: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    events: List[TrackingEventResponse] = Field(default_factory=list)

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
    payment_consent_at: Optional[datetime] = None
    payment_consent_version: Optional[str] = None
    items: List[OrderItemResponse]
    shipment: Optional[ShipmentResponse] = None
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


class ShipmentUpdate(BaseModel):
    provider: Optional[str] = Field(default=None, max_length=30)
    provider_shipment_id: Optional[str] = Field(default=None, max_length=100)
    awb_code: Optional[str] = Field(default=None, max_length=100)
    courier_name: Optional[str] = Field(default=None, max_length=120)
    status: Optional[str] = Field(default=None, max_length=40)
    tracking_url: Optional[str] = Field(default=None, max_length=500)
    estimated_delivery: Optional[datetime] = None
    event_title: Optional[str] = Field(default=None, max_length=160)
    event_description: Optional[str] = None
    event_location: Optional[str] = Field(default=None, max_length=200)
    occurred_at: Optional[datetime] = None


class PublicTrackingResponse(BaseModel):
    order_number: str
    order_status: str
    destination_city: Optional[str] = None
    item_count: int
    shipment: ShipmentResponse
