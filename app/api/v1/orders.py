from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload
from uuid import UUID
from decimal import Decimal
import secrets
import string
from datetime import datetime
from app.db.session import get_db
from app.core.pricing import included_gst
from app.api.deps import get_current_active_user, require_permission
from app.core.permissions import Permission
from app.core.cache import CacheInvalidator
from app.models.order import Order, OrderItem, OrderStatus, Shipment, TrackingEvent
from app.models.product import Product
from app.models.address import Address
from app.models.cart import CartItem
from app.models.user import User
from app.services import shiprocket
from app.schemas.order import (
    OrderCreate,
    OrderResponse,
    OrderListResponse,
    OrderStatusUpdate,
    PublicTrackingResponse,
    ShipmentResponse,
    ShipmentUpdate,
)

router = APIRouter()

SHIPPING_COST = Decimal("0")  # Free shipping
# Orders a customer has paid for; tracking links only work for these.
PAID_ORDER_STATUSES = {
    OrderStatus.CONFIRMED.value,
    OrderStatus.PROCESSING.value,
    OrderStatus.SHIPPED.value,
    OrderStatus.DELIVERED.value,
}
SHIPMENT_STATUSES = {
    "order_confirmed",
    "processing",
    "ready_to_ship",
    "picked_up",
    "in_transit",
    "out_for_delivery",
    "delivered",
    "delivery_delayed",
    "ndr",
    "rto_in_transit",
    "rto_delivered",
    "cancelled",
}


def generate_order_number() -> str:
    """Generate unique order number"""
    timestamp = datetime.utcnow().strftime("%Y%m%d")
    random_suffix = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    return f"ORD-{timestamp}-{random_suffix}"


def address_to_dict(address: Address) -> dict:
    return {
        "full_name": address.full_name,
        "phone": address.phone,
        "address_line1": address.address_line1,
        "address_line2": address.address_line2,
        "city": address.city,
        "state": address.state,
        "postal_code": address.postal_code,
        "country": address.country
    }


def get_or_create_shipment(db: Session, order: Order) -> Shipment:
    if order.shipment:
        return order.shipment

    shipment = Shipment(order_id=order.id)
    db.add(shipment)
    db.flush()
    db.add(TrackingEvent(
        shipment_id=shipment.id,
        status="order_confirmed",
        title="Order confirmed",
        description="We received your order and are preparing it for dispatch.",
        occurred_at=order.created_at or datetime.utcnow(),
    ))
    return shipment


@router.get("/", response_model=OrderListResponse)
def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    status: str = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    query = db.query(Order).options(
        joinedload(Order.shipment).joinedload(Shipment.events)
    ).filter(Order.user_id == current_user.id)

    if status:
        query = query.filter(Order.status == status)

    total = query.count()
    offset = (page - 1) * page_size

    orders = query.order_by(Order.created_at.desc()).offset(offset).limit(page_size).all()

    return OrderListResponse(
        items=orders,
        total=total,
        page=page,
        page_size=page_size
    )


# Static routes must be declared before /{order_id}; otherwise "admin" and
# "track" are treated as UUID values by Starlette's first-match routing.
@router.get("/admin/all", response_model=OrderListResponse)
def list_all_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str = None,
    current_user: User = Depends(require_permission(Permission.MANAGE_ALL_ORDERS)),
    db: Session = Depends(get_db)
):
    query = db.query(Order).options(
        joinedload(Order.shipment).joinedload(Shipment.events)
    )

    if status:
        query = query.filter(Order.status == status)

    total = query.count()
    offset = (page - 1) * page_size
    orders = query.order_by(Order.created_at.desc()).offset(offset).limit(page_size).all()
    return OrderListResponse(items=orders, total=total, page=page, page_size=page_size)


@router.get("/track/{tracking_token}", response_model=PublicTrackingResponse)
def get_public_tracking(tracking_token: str, db: Session = Depends(get_db)):
    shipment = db.query(Shipment).options(
        joinedload(Shipment.events), joinedload(Shipment.order).joinedload(Order.items)
    ).filter(Shipment.tracking_token == tracking_token).first()
    # Unpaid orders get the same 404, so the link reveals nothing until payment clears.
    if not shipment or shipment.order.status not in PAID_ORDER_STATUSES:
        raise HTTPException(status_code=404, detail="Tracking link not found")

    order = shipment.order
    return PublicTrackingResponse(
        order_number=order.order_number,
        order_status=order.status,
        destination_city=order.shipping_address.get("city"),
        item_count=sum(item.quantity for item in order.items),
        shipment=ShipmentResponse.model_validate(shipment),
    )


@router.put("/admin/{order_id}/shipment", response_model=OrderResponse)
def update_shipment(
    order_id: UUID,
    shipment_update: ShipmentUpdate,
    current_user: User = Depends(require_permission(Permission.MANAGE_ALL_ORDERS)),
    db: Session = Depends(get_db),
):
    order = db.query(Order).options(joinedload(Order.shipment)).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if shipment_update.status and shipment_update.status not in SHIPMENT_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid shipment status")

    shipment = get_or_create_shipment(db, order)
    for field in (
        "provider", "provider_shipment_id", "awb_code", "courier_name",
        "status", "tracking_url", "estimated_delivery",
    ):
        value = getattr(shipment_update, field)
        if value is not None:
            setattr(shipment, field, value)

    if shipment_update.status:
        shipment.last_synced_at = datetime.utcnow()
        if shipment_update.status in {"picked_up", "in_transit", "out_for_delivery"}:
            order.status = OrderStatus.SHIPPED.value
        elif shipment_update.status == "delivered":
            order.status = OrderStatus.DELIVERED.value

    if shipment_update.event_title:
        db.add(TrackingEvent(
            shipment_id=shipment.id,
            status=shipment_update.status or shipment.status,
            title=shipment_update.event_title,
            description=shipment_update.event_description,
            location=shipment_update.event_location,
            occurred_at=shipment_update.occurred_at or datetime.utcnow(),
        ))

    db.commit()
    return db.query(Order).options(
        joinedload(Order.shipment).joinedload(Shipment.events)
    ).filter(Order.id == order.id).first()


@router.post("/admin/{order_id}/shipment/shiprocket", response_model=OrderResponse)
def push_to_shiprocket(
    order_id: UUID,
    current_user: User = Depends(require_permission(Permission.MANAGE_ALL_ORDERS)),
    db: Session = Depends(get_db),
):
    """Create (or finish creating) this order in Shiprocket. Safe to retry."""
    order = shiprocket.load_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        shiprocket.push_order(db, order)
    except shiprocket.ShiprocketError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc))
    return shiprocket.load_order(db, order_id)


@router.post("/admin/{order_id}/shipment/refresh", response_model=OrderResponse)
def refresh_shipment_tracking(
    order_id: UUID,
    current_user: User = Depends(require_permission(Permission.MANAGE_ALL_ORDERS)),
    db: Session = Depends(get_db),
):
    """Pull the latest courier scans from Shiprocket, for when a webhook was missed."""
    order = shiprocket.load_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        shiprocket.refresh_tracking(db, order)
    except shiprocket.ShiprocketError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc))
    return shiprocket.load_order(db, order_id)


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    order = db.query(Order).options(
        joinedload(Order.shipment).joinedload(Shipment.events)
    ).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Check ownership or admin permission
    if order.user_id != current_user.id:
        from app.core.permissions import get_role_permissions, Permission
        user_permissions = get_role_permissions(current_user.role.name)
        if Permission.MANAGE_ALL_ORDERS not in user_permissions:
            raise HTTPException(status_code=403, detail="Not authorized")

    return order


@router.post("/", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(
    order_data: OrderCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create order with atomic stock reservation.

    Edge cases handled:
    1. Race condition: SELECT FOR UPDATE locks product rows
    2. Double-submit: Idempotency key prevents duplicate orders
    3. Deadlock: Products locked in sorted order
    4. Price changes: Price captured at order time
    """

    # EDGE CASE 1: Double-submit prevention with idempotency key
    if order_data.idempotency_key:
        existing_order = db.query(Order).filter(
            Order.idempotency_key == order_data.idempotency_key,
            Order.user_id == current_user.id,
        ).first()
        if existing_order:
            # Return existing order instead of creating duplicate
            return existing_order

    if not order_data.payment_consent:
        raise HTTPException(
            status_code=400,
            detail="Payment consent is required before an order can be created",
        )

    # Get shipping address
    shipping_address = db.query(Address).filter(
        Address.id == order_data.shipping_address_id,
        Address.user_id == current_user.id
    ).first()
    if not shipping_address:
        raise HTTPException(status_code=404, detail="Shipping address not found")

    # Get billing address (or use shipping)
    billing_address = None
    if order_data.billing_address_id:
        billing_address = db.query(Address).filter(
            Address.id == order_data.billing_address_id,
            Address.user_id == current_user.id
        ).first()

    # Collect product IDs for locking
    product_ids = [item.product_id for item in order_data.items]

    # EDGE CASE 2: Deadlock prevention - always lock in consistent order
    # EDGE CASE 3: Race condition prevention with SELECT FOR UPDATE
    # This prevents two users from buying the last item simultaneously
    products = db.query(Product).filter(
        Product.id.in_(product_ids),
        Product.is_active == True
    ).order_by(Product.id).with_for_update().all()  # Sorted + FOR UPDATE

    # Create product lookup dict
    product_map = {str(p.id): p for p in products}

    # Validate all products exist
    for item_data in order_data.items:
        if str(item_data.product_id) not in product_map:
            raise HTTPException(
                status_code=404,
                detail=f"Product {item_data.product_id} not found"
            )

    # Create order items and calculate totals (now with locked rows)
    order_items = []
    subtotal = Decimal("0")
    stock_errors = []

    for item_data in order_data.items:
        product = product_map[str(item_data.product_id)]

        # Check stock (row is locked, so this is accurate)
        if product.stock_quantity < item_data.quantity:
            stock_errors.append(
                f"{product.name}: only {product.stock_quantity} available"
            )
            continue

        item_subtotal = product.price * item_data.quantity
        subtotal += item_subtotal

        # EDGE CASE 4: Price lock - capture price NOW, not at payment time
        order_items.append(OrderItem(
            product_id=product.id,
            product_name=product.name,
            quantity=item_data.quantity,
            unit_price=product.price,  # Price locked at order creation
            subtotal=item_subtotal,
            attributes=item_data.attributes
        ))

        # Reserve stock (will be confirmed after payment or restored on failure)
        product.stock_quantity -= item_data.quantity

    # If any stock errors, rollback and report
    if stock_errors:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient stock: {'; '.join(stock_errors)}"
        )

    # Prices already include GST; report the included share without adding it.
    tax = included_gst(subtotal)
    total = subtotal + SHIPPING_COST

    # Create order
    order = Order(
        order_number=generate_order_number(),
        idempotency_key=order_data.idempotency_key,  # Store for duplicate prevention
        user_id=current_user.id,
        status=OrderStatus.PENDING.value,
        stock_reserved="yes",  # Track that stock has been reserved
        subtotal=subtotal,
        tax=tax,
        shipping_cost=SHIPPING_COST,
        total=total,
        shipping_address=address_to_dict(shipping_address),
        billing_address=address_to_dict(billing_address) if billing_address else None,
        customer_notes=order_data.customer_notes,
        payment_consent_at=datetime.utcnow(),
        payment_consent_version=order_data.payment_consent_version or "razorpay_checkout_v1",
    )

    db.add(order)
    db.flush()  # Get order ID

    shipment = Shipment(order_id=order.id)
    db.add(shipment)
    db.flush()
    db.add(TrackingEvent(
        shipment_id=shipment.id,
        status="order_confirmed",
        title="Order confirmed",
        description="We received your order and are preparing it for dispatch.",
        occurred_at=datetime.utcnow(),
    ))

    # Link items to order
    for item in order_items:
        item.order_id = order.id
        db.add(item)

    # Clear user's cart
    db.query(CartItem).filter(CartItem.user_id == current_user.id).delete()

    db.commit()
    db.refresh(order)

    # Invalidate product caches (stock changed)
    for product_id in product_ids:
        product = product_map.get(str(product_id))
        if product:
            CacheInvalidator.invalidate_product(str(product_id), product.slug)

    return order


@router.post("/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(
    order_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Cancel order with proper locking to prevent double-cancel.

    Edge cases handled:
    1. Double-cancel: Lock order row + check stock_reserved flag
    2. Race condition: Lock products before restoring stock
    """

    # EDGE CASE: Lock order row to prevent double-cancel
    order = db.query(Order).filter(
        Order.id == order_id
    ).with_for_update().first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Can only cancel pending or confirmed orders
    if order.status not in [OrderStatus.PENDING.value, OrderStatus.CONFIRMED.value]:
        raise HTTPException(
            status_code=400,
            detail="Order cannot be cancelled at this stage"
        )

    # EDGE CASE: Only restore stock if it was reserved and not already restored
    if order.stock_reserved == "yes":
        # Lock products in order to prevent race conditions
        product_ids = [item.product_id for item in order.items]
        products = db.query(Product).filter(
            Product.id.in_(product_ids)
        ).order_by(Product.id).with_for_update().all()

        product_map = {str(p.id): p for p in products}

        # Restore stock
        for item in order.items:
            product = product_map.get(str(item.product_id))
            if product:
                product.stock_quantity += item.quantity

        order.stock_reserved = "restored"  # Mark as restored to prevent double-restore

        # Invalidate caches
        for product_id in product_ids:
            product = product_map.get(str(product_id))
            if product:
                CacheInvalidator.invalidate_product(str(product_id), product.slug)

    order.status = OrderStatus.CANCELLED.value
    shipment = get_or_create_shipment(db, order)
    shipment.status = "cancelled"
    shipment.last_synced_at = datetime.utcnow()
    db.add(TrackingEvent(
        shipment_id=shipment.id,
        status="cancelled",
        title="Order cancelled",
        description="This order was cancelled before dispatch.",
        occurred_at=datetime.utcnow(),
    ))
    db.commit()
    db.refresh(order)

    return order


@router.put("/{order_id}/status", response_model=OrderResponse)
def update_order_status(
    order_id: UUID,
    status_update: OrderStatusUpdate,
    current_user: User = Depends(require_permission(Permission.MANAGE_ALL_ORDERS)),
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Validate status transition
    valid_statuses = [s.value for s in OrderStatus]
    if status_update.status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Invalid status")

    previous_status = order.status

    if status_update.status == OrderStatus.CANCELLED.value and order.stock_reserved == "yes":
        product_ids = [item.product_id for item in order.items]
        products = db.query(Product).filter(Product.id.in_(product_ids)).order_by(Product.id).with_for_update().all()
        product_map = {str(product.id): product for product in products}
        for item in order.items:
            product = product_map.get(str(item.product_id))
            if product:
                product.stock_quantity += item.quantity
                CacheInvalidator.invalidate_product(str(product.id), product.slug)
        order.stock_reserved = "restored"

    order.status = status_update.status
    if status_update.admin_notes:
        order.admin_notes = status_update.admin_notes

    shipment_status_map = {
        OrderStatus.CONFIRMED.value: ("order_confirmed", "Order confirmed"),
        OrderStatus.PROCESSING.value: ("processing", "Preparing your order"),
        OrderStatus.SHIPPED.value: ("in_transit", "Order dispatched"),
        OrderStatus.DELIVERED.value: ("delivered", "Order delivered"),
        OrderStatus.CANCELLED.value: ("cancelled", "Order cancelled"),
    }
    if previous_status != status_update.status and status_update.status in shipment_status_map:
        shipment_status, title = shipment_status_map[status_update.status]
        shipment = get_or_create_shipment(db, order)
        shipment.status = shipment_status
        shipment.last_synced_at = datetime.utcnow()
        db.add(TrackingEvent(
            shipment_id=shipment.id,
            status=shipment_status,
            title=title,
            description=status_update.admin_notes,
            occurred_at=datetime.utcnow(),
        ))

    db.commit()
    db.refresh(order)

    return order
