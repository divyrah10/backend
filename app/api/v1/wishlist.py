from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from app.db.session import get_db
from app.api.deps import get_current_active_user
from app.models.wishlist import Wishlist
from app.models.product import Product
from app.models.user import User
from app.schemas.wishlist import WishlistResponse, WishlistItemResponse

router = APIRouter()


@router.get("/", response_model=WishlistResponse)
def get_wishlist(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    wishlist_items = db.query(Wishlist).filter(
        Wishlist.user_id == current_user.id
    ).all()

    items = []
    for item in wishlist_items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if product:
            items.append(WishlistItemResponse(
                id=item.id,
                product_id=product.id,
                product_name=product.name,
                product_slug=product.slug,
                product_image=product.images[0] if product.images else None,
                product_price=product.price,
                in_stock=product.in_stock,
                created_at=item.created_at
            ))

    return WishlistResponse(items=items, total_items=len(items))


@router.post("/{product_id}", status_code=status.HTTP_201_CREATED)
def add_to_wishlist(
    product_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Check product exists
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.is_active == True
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Check if already in wishlist
    existing = db.query(Wishlist).filter(
        Wishlist.user_id == current_user.id,
        Wishlist.product_id == product_id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Product already in wishlist")

    wishlist_item = Wishlist(
        user_id=current_user.id,
        product_id=product_id
    )
    db.add(wishlist_item)
    db.commit()

    return {"message": "Product added to wishlist"}


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_wishlist(
    product_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    wishlist_item = db.query(Wishlist).filter(
        Wishlist.user_id == current_user.id,
        Wishlist.product_id == product_id
    ).first()

    if not wishlist_item:
        raise HTTPException(status_code=404, detail="Item not in wishlist")

    db.delete(wishlist_item)
    db.commit()


@router.get("/check/{product_id}")
def check_in_wishlist(
    product_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    exists = db.query(Wishlist).filter(
        Wishlist.user_id == current_user.id,
        Wishlist.product_id == product_id
    ).first() is not None

    return {"in_wishlist": exists}
