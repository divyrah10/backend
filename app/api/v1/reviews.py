from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from uuid import UUID
from app.db.session import get_db
from app.api.deps import get_current_active_user, require_permission
from app.core.permissions import Permission
from app.models.review import Review
from app.models.product import Product
from app.models.order import Order, OrderItem
from app.models.user import User
from app.schemas.review import ReviewCreate, ReviewUpdate, ReviewResponse, ProductReviewStats

router = APIRouter()


@router.get("/product/{product_id}", response_model=List[ReviewResponse])
def get_product_reviews(
    product_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    offset = (page - 1) * page_size

    reviews = db.query(Review).filter(
        Review.product_id == product_id,
        Review.is_approved == True
    ).order_by(Review.created_at.desc()).offset(offset).limit(page_size).all()

    result = []
    for review in reviews:
        user = db.query(User).filter(User.id == review.user_id).first()
        result.append(ReviewResponse(
            id=review.id,
            product_id=review.product_id,
            user_id=review.user_id,
            user_name=user.full_name if user else "Anonymous",
            rating=review.rating,
            title=review.title,
            comment=review.comment,
            is_verified_purchase=review.is_verified_purchase,
            is_approved=review.is_approved,
            created_at=review.created_at
        ))

    return result


@router.get("/product/{product_id}/stats", response_model=ProductReviewStats)
def get_product_review_stats(product_id: UUID, db: Session = Depends(get_db)):
    reviews = db.query(Review).filter(
        Review.product_id == product_id,
        Review.is_approved == True
    ).all()

    if not reviews:
        return ProductReviewStats(
            average_rating=0,
            total_reviews=0,
            rating_distribution={1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        )

    total = len(reviews)
    avg = sum(r.rating for r in reviews) / total

    distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for review in reviews:
        distribution[review.rating] += 1

    return ProductReviewStats(
        average_rating=round(avg, 1),
        total_reviews=total,
        rating_distribution=distribution
    )


@router.post("/", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
def create_review(
    review_data: ReviewCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Check product exists
    product = db.query(Product).filter(Product.id == review_data.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Check if user already reviewed this product
    existing = db.query(Review).filter(
        Review.product_id == review_data.product_id,
        Review.user_id == current_user.id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="You have already reviewed this product")

    # Check if verified purchase
    is_verified = db.query(OrderItem).join(Order).filter(
        Order.user_id == current_user.id,
        OrderItem.product_id == review_data.product_id,
        Order.status == "delivered"
    ).first() is not None

    review = Review(
        product_id=review_data.product_id,
        user_id=current_user.id,
        rating=review_data.rating,
        title=review_data.title,
        comment=review_data.comment,
        is_verified_purchase=is_verified,
        is_approved=False  # Requires admin approval
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    return ReviewResponse(
        id=review.id,
        product_id=review.product_id,
        user_id=review.user_id,
        user_name=current_user.full_name,
        rating=review.rating,
        title=review.title,
        comment=review.comment,
        is_verified_purchase=review.is_verified_purchase,
        is_approved=review.is_approved,
        created_at=review.created_at
    )


@router.put("/{review_id}", response_model=ReviewResponse)
def update_review(
    review_id: UUID,
    review_data: ReviewUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    # Only owner can update (except approval status)
    if review.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    update_data = review_data.model_dump(exclude_unset=True, exclude={"is_approved"})
    for field, value in update_data.items():
        setattr(review, field, value)

    db.commit()
    db.refresh(review)

    return ReviewResponse(
        id=review.id,
        product_id=review.product_id,
        user_id=review.user_id,
        user_name=current_user.full_name,
        rating=review.rating,
        title=review.title,
        comment=review.comment,
        is_verified_purchase=review.is_verified_purchase,
        is_approved=review.is_approved,
        created_at=review.created_at
    )


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(
    review_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    if review.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    db.delete(review)
    db.commit()


# Admin endpoints
@router.get("/pending", response_model=List[ReviewResponse])
def get_pending_reviews(
    current_user: User = Depends(require_permission(Permission.APPROVE_REVIEWS)),
    db: Session = Depends(get_db)
):
    reviews = db.query(Review).filter(Review.is_approved == False).all()

    result = []
    for review in reviews:
        user = db.query(User).filter(User.id == review.user_id).first()
        result.append(ReviewResponse(
            id=review.id,
            product_id=review.product_id,
            user_id=review.user_id,
            user_name=user.full_name if user else "Anonymous",
            rating=review.rating,
            title=review.title,
            comment=review.comment,
            is_verified_purchase=review.is_verified_purchase,
            is_approved=review.is_approved,
            created_at=review.created_at
        ))

    return result


@router.post("/{review_id}/approve", response_model=ReviewResponse)
def approve_review(
    review_id: UUID,
    current_user: User = Depends(require_permission(Permission.APPROVE_REVIEWS)),
    db: Session = Depends(get_db)
):
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    review.is_approved = True
    db.commit()
    db.refresh(review)

    user = db.query(User).filter(User.id == review.user_id).first()
    return ReviewResponse(
        id=review.id,
        product_id=review.product_id,
        user_id=review.user_id,
        user_name=user.full_name if user else "Anonymous",
        rating=review.rating,
        title=review.title,
        comment=review.comment,
        is_verified_purchase=review.is_verified_purchase,
        is_approved=review.is_approved,
        created_at=review.created_at
    )


@router.post("/{review_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
def reject_review(
    review_id: UUID,
    current_user: User = Depends(require_permission(Permission.APPROVE_REVIEWS)),
    db: Session = Depends(get_db)
):
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    db.delete(review)
    db.commit()
