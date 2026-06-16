from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from decimal import Decimal
from datetime import datetime


class WishlistItemResponse(BaseModel):
    id: UUID
    product_id: UUID
    product_name: str
    product_slug: str
    product_image: Optional[str]
    product_price: Decimal
    in_stock: bool
    created_at: datetime

    class Config:
        from_attributes = True


class WishlistResponse(BaseModel):
    items: List[WishlistItemResponse]
    total_items: int
