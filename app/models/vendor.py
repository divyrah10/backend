import uuid
from sqlalchemy import Column, String, Text, Boolean, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base, TimestampMixin


class Vendor(Base, TimestampMixin):
    __tablename__ = "vendors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    slug = Column(String(220), unique=True, nullable=False, index=True)
    logo_url = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    commission_rate = Column(Numeric(5, 2), default=0.00)  # Percentage
    is_active = Column(Boolean, default=True)

    # Relationships
    products = relationship("Product", back_populates="vendor")

    def __repr__(self):
        return f"<Vendor {self.name}>"
