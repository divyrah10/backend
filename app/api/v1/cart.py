from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID
from decimal import Decimal
from app.db.session import get_db
from app.core.pricing import included_gst
from app.api.deps import get_current_user
from app.models.cart import CartItem
from app.models.product import Product
from app.services import inventory
from app.models.user import User
from app.schemas.cart import CartItemCreate, CartItemUpdate, CartItemResponse, CartResponse

router = APIRouter()



def get_cart_items(db: Session, user: Optional[User], session_id: Optional[str]):
    """Get cart items for user or session"""
    query = db.query(CartItem)

    if user:
        query = query.filter(CartItem.user_id == user.id)
    elif session_id:
        query = query.filter(CartItem.session_id == session_id)
    else:
        return []

    return query.all()


def build_cart_response(cart_items: list, db: Session) -> CartResponse:
    """Build cart response with totals"""
    items = []
    subtotal = Decimal("0")

    for item in cart_items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if not product:
            continue

        item_subtotal = product.price * item.quantity
        subtotal += item_subtotal

        items.append(CartItemResponse(
            id=item.id,
            product_id=product.id,
            product_name=product.name,
            product_slug=product.slug,
            product_sku=product.sku,
            product_image=product.images[0] if product.images else None,
            product_price=product.price,
            quantity=item.quantity,
            attributes=item.attributes or {},
            subtotal=item_subtotal
        ))

    # Prices already include GST; report the included share without adding it.
    tax = included_gst(subtotal)
    total = subtotal

    return CartResponse(
        items=items,
        total_items=len(items),
        subtotal=subtotal,
        tax=tax,
        total=total
    )


@router.get("/", response_model=CartResponse)
def get_cart(
    x_session_id: Optional[str] = Header(None),
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    cart_items = get_cart_items(db, current_user, x_session_id)
    return build_cart_response(cart_items, db)


@router.post("/items", response_model=CartResponse, status_code=status.HTTP_201_CREATED)
def add_to_cart(
    item_data: CartItemCreate,
    x_session_id: Optional[str] = Header(None),
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Check product exists and is active
    product = db.query(Product).filter(
        Product.id == item_data.product_id,
        Product.is_active == True
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if not product.in_stock:
        raise HTTPException(status_code=400, detail="Product is out of stock")

    available_sizes = inventory.product_sizes(product)
    selected_size = inventory.item_size(item_data.attributes)
    if available_sizes and selected_size not in available_sizes:
        raise HTTPException(status_code=400, detail="Please select an available size")

    stock = inventory.available(product, selected_size)
    if stock <= 0:
        raise HTTPException(status_code=400, detail=f"Size {selected_size} is sold out")
    if item_data.quantity > stock:
        raise HTTPException(status_code=400, detail=f"Only {stock} items available")

    # Check if item already in cart
    query = db.query(CartItem).filter(
        CartItem.product_id == item_data.product_id,
        CartItem.attributes == item_data.attributes,
    )
    if current_user:
        query = query.filter(CartItem.user_id == current_user.id)
    elif x_session_id:
        query = query.filter(CartItem.session_id == x_session_id)
    else:
        raise HTTPException(status_code=400, detail="Session ID required for guest cart")

    existing_item = query.first()

    if existing_item:
        # Update quantity
        new_quantity = existing_item.quantity + item_data.quantity
        if new_quantity > stock:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot add more. Only {stock} items available"
            )
        existing_item.quantity = new_quantity
    else:
        # Create new cart item
        cart_item = CartItem(
            user_id=current_user.id if current_user else None,
            session_id=x_session_id if not current_user else None,
            product_id=item_data.product_id,
            quantity=item_data.quantity,
            attributes=item_data.attributes
        )
        db.add(cart_item)

    db.commit()

    cart_items = get_cart_items(db, current_user, x_session_id)
    return build_cart_response(cart_items, db)


@router.put("/items/{item_id}", response_model=CartResponse)
def update_cart_item(
    item_id: UUID,
    item_data: CartItemUpdate,
    x_session_id: Optional[str] = Header(None),
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(CartItem).filter(CartItem.id == item_id)
    if current_user:
        query = query.filter(CartItem.user_id == current_user.id)
    elif x_session_id:
        query = query.filter(CartItem.session_id == x_session_id)

    cart_item = query.first()
    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    # Check stock
    product = db.query(Product).filter(Product.id == cart_item.product_id).first()
    stock = inventory.available(product, inventory.item_size(cart_item.attributes))
    if item_data.quantity > stock:
        raise HTTPException(
            status_code=400,
            detail=f"Only {stock} items available"
        )

    if item_data.quantity <= 0:
        db.delete(cart_item)
    else:
        cart_item.quantity = item_data.quantity

    db.commit()

    cart_items = get_cart_items(db, current_user, x_session_id)
    return build_cart_response(cart_items, db)


@router.delete("/items/{item_id}", response_model=CartResponse)
def remove_from_cart(
    item_id: UUID,
    x_session_id: Optional[str] = Header(None),
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(CartItem).filter(CartItem.id == item_id)
    if current_user:
        query = query.filter(CartItem.user_id == current_user.id)
    elif x_session_id:
        query = query.filter(CartItem.session_id == x_session_id)

    cart_item = query.first()
    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    db.delete(cart_item)
    db.commit()

    cart_items = get_cart_items(db, current_user, x_session_id)
    return build_cart_response(cart_items, db)


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
def clear_cart(
    x_session_id: Optional[str] = Header(None),
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(CartItem)
    if current_user:
        query = query.filter(CartItem.user_id == current_user.id)
    elif x_session_id:
        query = query.filter(CartItem.session_id == x_session_id)
    else:
        return

    query.delete()
    db.commit()


@router.post("/merge", response_model=CartResponse)
def merge_guest_cart(
    x_session_id: str = Header(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Merge guest cart into user cart after login"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get guest cart items
    guest_items = db.query(CartItem).filter(CartItem.session_id == x_session_id).all()

    for guest_item in guest_items:
        # Check if user already has this product
        existing = db.query(CartItem).filter(
            CartItem.user_id == current_user.id,
            CartItem.product_id == guest_item.product_id,
            CartItem.attributes == guest_item.attributes,
        ).first()

        if existing:
            # Merge quantities
            product = db.query(Product).filter(Product.id == guest_item.product_id).first()
            new_qty = min(existing.quantity + guest_item.quantity,
                          inventory.available(product, inventory.item_size(guest_item.attributes)))
            existing.quantity = new_qty
            db.delete(guest_item)
        else:
            # Transfer to user
            guest_item.user_id = current_user.id
            guest_item.session_id = None

    db.commit()

    cart_items = get_cart_items(db, current_user, None)
    return build_cart_response(cart_items, db)
