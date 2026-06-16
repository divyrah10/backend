from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class ReviewCreate(BaseModel):
    product_id: UUID
    rating: int = Field(..., ge=1, le=5)
    title: Optional[str] = None
    comment: Optional[str] = None


class ReviewUpdate(BaseModel):
    rating: Optional[int] = Field(None, ge=1, le=5)
    title: Optional[str] = None
    comment: Optional[str] = None
    is_approved: Optional[bool] = None


class ReviewResponse(BaseModel):
    id: UUID
    product_id: UUID
    user_id: UUID
    user_name: str
    rating: int
    title: Optional[str]
    comment: Optional[str]
    is_verified_purchase: bool
    is_approved: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ProductReviewStats(BaseModel):
    average_rating: float
    total_reviews: int
    rating_distribution: dict  # {1: count, 2: count, ...}
