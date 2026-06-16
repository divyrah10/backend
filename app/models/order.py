import uuid
from sqlalchemy import Column, String, Text, Integer, Numeric, ForeignKey, Enum
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

    # Notes
    customer_notes = Column(Text, nullable=True)
    admin_notes = Column(Text, nullable=True)

    # Relationships
    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    payment = relationship("Payment", back_populates="order")

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
