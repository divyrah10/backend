import uuid
from sqlalchemy import Column, String, Text, Boolean, Integer, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.base import Base, TimestampMixin


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(300), nullable=False)
    slug = Column(String(350), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    short_description = Column(String(500), nullable=True)

    # Pricing
    price = Column(Numeric(12, 2), nullable=False)
    compare_at_price = Column(Numeric(12, 2), nullable=True)  # Original price for showing discounts

    # Inventory
    sku = Column(String(100), unique=True, nullable=True, index=True)
    stock_quantity = Column(Integer, default=0)
    low_stock_threshold = Column(Integer, default=5)

    # Relations
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=True)

    # Media and attributes
    images = Column(JSONB, default=list)  # List of image URLs
    attributes = Column(JSONB, default=dict)  # {size: [...], color: [...], material: "..."}
    # Per-size stock, e.g. {"S": 4, "M": 7}. Empty means stock is tracked only in stock_quantity.
    size_stock = Column(JSONB, default=dict, nullable=False, server_default="{}")

    # Status
    is_active = Column(Boolean, default=True)
    is_featured = Column(Boolean, default=False)

    # SEO
    meta_title = Column(String(200), nullable=True)
    meta_description = Column(String(500), nullable=True)

    # Relationships
    category = relationship("Category", back_populates="products")
    vendor = relationship("Vendor", back_populates="products")
    cart_items = relationship("CartItem", back_populates="product", cascade="all, delete-orphan")
    wishlist_items = relationship("Wishlist", back_populates="product", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="product", cascade="all, delete-orphan")
    order_items = relationship("OrderItem", back_populates="product")

    def __repr__(self):
        return f"<Product {self.name}>"

    @property
    def is_on_sale(self) -> bool:
        return self.compare_at_price is not None and self.compare_at_price > self.price

    @property
    def discount_percentage(self) -> int:
        if self.is_on_sale:
            return int(((self.compare_at_price - self.price) / self.compare_at_price) * 100)
        return 0

    @property
    def in_stock(self) -> bool:
        return self.stock_quantity > 0
