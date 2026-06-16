import uuid
from sqlalchemy import Column, String, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base, TimestampMixin


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Razorpay fields
    razorpay_order_id = Column(String(100), nullable=True, index=True)
    razorpay_payment_id = Column(String(100), nullable=True, index=True)
    razorpay_signature = Column(String(500), nullable=True)

    # Payment details
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), default="INR")
    status = Column(String(20), default="pending")  # pending, completed, failed, refunded
    method = Column(String(50), nullable=True)  # card, upi, netbanking, etc.

    # Error tracking
    error_code = Column(String(50), nullable=True)
    error_description = Column(String(500), nullable=True)

    # Relationships
    order = relationship("Order", back_populates="payment", uselist=False)

    def __repr__(self):
        return f"<Payment {self.razorpay_payment_id} - {self.status}>"
