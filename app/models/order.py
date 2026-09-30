import secrets
import uuid
from sqlalchemy import Column, String, Text, Integer, Numeric, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.base import Base, TimestampMixin
import enum


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_number = Column(String(50), unique=True, nullable=False, index=True)
    idempotency_key = Column(String(100), unique=True, nullable=True, index=True)  # Prevents double-submit
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status = Column(String(20), default=OrderStatus.PENDING.value, nullable=False)
    stock_reserved = Column(String(10), default="no")  # "no", "yes", "restored" - tracks stock state

    # Pricing
    subtotal = Column(Numeric(12, 2), nullable=False)
    tax = Column(Numeric(12, 2), default=0)
    shipping_cost = Column(Numeric(12, 2), default=0)
    discount = Column(Numeric(12, 2), default=0)
    total = Column(Numeric(12, 2), nullable=False)

    # Addresses (stored as JSON for historical record)
    shipping_address = Column(JSONB, nullable=False)
    billing_address = Column(JSONB, nullable=True)

    # Payment
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id"), nullable=True)
    payment_consent_at = Column(DateTime, nullable=True)
    payment_consent_version = Column(String(50), nullable=True)

    # Notes
    customer_notes = Column(Text, nullable=True)
    admin_notes = Column(Text, nullable=True)

    # Relationships
    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    payment = relationship("Payment", back_populates="order")
    shipment = relationship(
        "Shipment",
        back_populates="order",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Order {self.order_number}>"


class OrderItem(Base, TimestampMixin):
    __tablename__ = "order_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    product_name = Column(String(300), nullable=False)  # Snapshot of product name
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)
    subtotal = Column(Numeric(12, 2), nullable=False)
    attributes = Column(JSONB, default=dict)  # Selected size, color, etc.

    # Relationships
    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")

    def __repr__(self):
        return f"<OrderItem {self.product_name} x{self.quantity}>"


class Shipment(Base, TimestampMixin):
    """Provider-neutral shipment data for one customer order."""

    __tablename__ = "shipments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), unique=True, nullable=False, index=True)
    tracking_token = Column(String(64), unique=True, nullable=False, index=True, default=lambda: secrets.token_urlsafe(32))
    provider = Column(String(30), default="shiprocket", nullable=False)
    provider_shipment_id = Column(String(100), nullable=True, index=True)
    awb_code = Column(String(100), nullable=True, index=True)
    courier_name = Column(String(120), nullable=True)
    status = Column(String(40), default="order_confirmed", nullable=False, index=True)
    tracking_url = Column(String(500), nullable=True)
    estimated_delivery = Column(DateTime, nullable=True)
    last_synced_at = Column(DateTime, nullable=True)

    order = relationship("Order", back_populates="shipment")
    events = relationship(
        "TrackingEvent",
        back_populates="shipment",
        cascade="all, delete-orphan",
        order_by="TrackingEvent.occurred_at.desc()",
    )


class TrackingEvent(Base, TimestampMixin):
    __tablename__ = "tracking_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shipment_id = Column(UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=False, index=True)
    status = Column(String(40), nullable=False, index=True)
    title = Column(String(160), nullable=False)
    description = Column(Text, nullable=True)
    location = Column(String(200), nullable=True)
    occurred_at = Column(DateTime, nullable=False)

    shipment = relationship("Shipment", back_populates="events")
