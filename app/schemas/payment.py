from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from decimal import Decimal
from datetime import datetime


class PaymentCreate(BaseModel):
    order_id: UUID
    currency: str = "INR"


class RazorpayOrderResponse(BaseModel):
    razorpay_order_id: str
    amount: int  # In paise
    currency: str
    key_id: str


class PaymentVerify(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    # Meta browser identifiers (_fbp/_fbc cookies) and page, for Conversions API matching.
    fbp: Optional[str] = None
    fbc: Optional[str] = None
    event_source_url: Optional[str] = None


class PaymentResponse(BaseModel):
    id: UUID
    razorpay_order_id: Optional[str]
    razorpay_payment_id: Optional[str]
    amount: Decimal
    currency: str
    status: str
    method: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
