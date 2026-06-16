from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from typing import Optional, List
from uuid import UUID
from app.db.session import get_db
from app.api.deps import get_current_user
from app.models.compare import CompareList
from app.models.product import Product
from app.models.user import User
from app.schemas.product import ProductResponse

router = APIRouter()

MAX_COMPARE_ITEMS = 4


@router.get("/", response_model=List[ProductResponse])
def get_compare_list(
    x_session_id: Optional[str] = Header(None),
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(CompareList)

    if current_user:
        query = query.filter(CompareList.user_id == current_user.id)
    elif x_session_id:
        query = query.filter(CompareList.session_id == x_session_id)
    else:
        return []

    compare_items = query.all()
    products = []

    for item in compare_items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if product and product.is_active:
            products.append(product)

    return products


@router.post("/{product_id}", status_code=status.HTTP_201_CREATED)
def add_to_compare(
    product_id: UUID,
    x_session_id: Optional[str] = Header(None),
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Check product exists
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.is_active == True
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Build query for existing items
    query = db.query(CompareList)
    if current_user:
        query = query.filter(CompareList.user_id == current_user.id)
    elif x_session_id:
        query = query.filter(CompareList.session_id == x_session_id)
    else:
        raise HTTPException(status_code=400, detail="Session ID required")

    # Check if already in compare list
    existing = query.filter(CompareList.product_id == product_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Product already in compare list")

    # Check max items
    count = query.count()
    if count >= MAX_COMPARE_ITEMS:
        raise HTTPException(
            status_code=400,
            detail=f"Compare list can have maximum {MAX_COMPARE_ITEMS} items"
        )

    compare_item = CompareList(
        user_id=current_user.id if current_user else None,
        session_id=x_session_id if not current_user else None,
        product_id=product_id
    )
    db.add(compare_item)
    db.commit()

    return {"message": "Product added to compare list"}


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_compare(
    product_id: UUID,
    x_session_id: Optional[str] = Header(None),
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(CompareList).filter(CompareList.product_id == product_id)

    if current_user:
        query = query.filter(CompareList.user_id == current_user.id)
    elif x_session_id:
        query = query.filter(CompareList.session_id == x_session_id)

    compare_item = query.first()
    if not compare_item:
        raise HTTPException(status_code=404, detail="Item not in compare list")

    db.delete(compare_item)
    db.commit()


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
def clear_compare_list(
    x_session_id: Optional[str] = Header(None),
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(CompareList)

    if current_user:
        query = query.filter(CompareList.user_id == current_user.id)
    elif x_session_id:
        query = query.filter(CompareList.session_id == x_session_id)
    else:
        return

    query.delete()
    db.commit()
