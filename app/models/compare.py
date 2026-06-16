import uuid
from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base, TimestampMixin


class CompareList(Base, TimestampMixin):
    __tablename__ = "compare_list"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    session_id = Column(String(100), nullable=True, index=True)  # For guest users
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)

    # Relationships
    product = relationship("Product")

    def __repr__(self):
        return f"<CompareList product={self.product_id}>"
