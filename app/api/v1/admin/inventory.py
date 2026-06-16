from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from app.db.session import get_db
from app.api.deps import require_permission
from app.core.permissions import Permission
from app.models.product import Product
from app.models.user import User
from pydantic import BaseModel

router = APIRouter()


class StockUpdate(BaseModel):
    quantity: int


class InventoryItem(BaseModel):
    id: UUID
    name: str
    sku: str | None
    stock_quantity: int
    low_stock_threshold: int
    is_low_stock: bool
    image: str | None

    class Config:
        from_attributes = True


@router.get("/", response_model=List[InventoryItem])
def list_inventory(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    low_stock_only: bool = False,
    search: str = None,
    current_user: User = Depends(require_permission(Permission.MANAGE_PRODUCTS)),
    db: Session = Depends(get_db)
):
    query = db.query(Product).filter(Product.is_active == True)

    if low_stock_only:
        query = query.filter(Product.stock_quantity <= Product.low_stock_threshold)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Product.name.ilike(search_term)) | (Product.sku.ilike(search_term))
        )

    offset = (page - 1) * page_size
    products = query.order_by(Product.stock_quantity.asc()).offset(offset).limit(page_size).all()

    return [InventoryItem(
        id=p.id,
        name=p.name,
        sku=p.sku,
        stock_quantity=p.stock_quantity,
        low_stock_threshold=p.low_stock_threshold,
        is_low_stock=p.stock_quantity <= p.low_stock_threshold,
        image=p.images[0] if p.images else None
    ) for p in products]


@router.put("/{product_id}/stock")
def update_stock(
    product_id: UUID,
    stock_data: StockUpdate,
    current_user: User = Depends(require_permission(Permission.MANAGE_PRODUCTS)),
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if stock_data.quantity < 0:
        raise HTTPException(status_code=400, detail="Stock quantity cannot be negative")

    product.stock_quantity = stock_data.quantity
    db.commit()

    return {
        "id": str(product.id),
        "name": product.name,
        "stock_quantity": product.stock_quantity,
        "message": "Stock updated successfully"
    }


@router.post("/{product_id}/add-stock")
def add_stock(
    product_id: UUID,
    stock_data: StockUpdate,
    current_user: User = Depends(require_permission(Permission.MANAGE_PRODUCTS)),
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product.stock_quantity += stock_data.quantity
    db.commit()

    return {
        "id": str(product.id),
        "name": product.name,
        "stock_quantity": product.stock_quantity,
        "message": f"Added {stock_data.quantity} units to stock"
    }


@router.get("/low-stock-count")
def get_low_stock_count(
    current_user: User = Depends(require_permission(Permission.MANAGE_PRODUCTS)),
    db: Session = Depends(get_db)
):
    count = db.query(Product).filter(
        Product.is_active == True,
        Product.stock_quantity <= Product.low_stock_threshold
    ).count()

    return {"low_stock_count": count}
