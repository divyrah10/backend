from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session
from uuid import UUID
import razorpay
import hmac
import hashlib
import json
from app.db.session import get_db
from app.api.deps import get_current_active_user
from app.core.config import settings
from app.core.cache import CacheInvalidator
from app.models.payment import Payment
from app.models.order import Order, OrderStatus
from app.models.product import Product
from app.models.user import User
from app.schemas.payment import PaymentCreate, PaymentResponse, RazorpayOrderResponse, PaymentVerify
from app.services.shiprocket import push_order_in_background

router = APIRouter()


def restore_order_stock(order: Order, db: Session):
    """Restore stock when payment fails - with proper locking"""
    if order.stock_reserved != "yes":
        return  # Stock wasn't reserved or already restored

    # Lock products in order
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

    order.stock_reserved = "restored"

    # Invalidate caches
    for product_id in product_ids:
        product = product_map.get(str(product_id))
        if product:
            CacheInvalidator.invalidate_product(str(product_id), product.slug)

# Initialize Razorpay client
razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def order_for_payment(db: Session, payment: Payment, lock: bool = False):
    """The order a payment belongs to.

    Orders created before the payment_id flush fix were never linked, so fall back
    to the order id we stored in the Razorpay order's notes, and repair the link.
    """
    query = db.query(Order)
    if lock:
        query = query.with_for_update()
    order = query.filter(Order.payment_id == payment.id).first()
    if order or not payment.razorpay_order_id:
        return order

    try:
        notes = razorpay_client.order.fetch(payment.razorpay_order_id).get("notes") or {}
    except Exception:
        return None
    order_id = notes.get("order_id")
    if not order_id:
        return None
    query = db.query(Order)
    if lock:
        query = query.with_for_update()
    order = query.filter(Order.id == order_id, Order.payment_id.is_(None)).first()
    if order:
        order.payment_id = payment.id
    return order


@router.post("/create-order", response_model=RazorpayOrderResponse)
def create_payment_order(
    payment_data: PaymentCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Get order
    order = db.query(Order).filter(Order.id == payment_data.order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    if order.status != OrderStatus.PENDING.value:
        raise HTTPException(status_code=400, detail="Order is not pending payment")

    # Create Razorpay order (amount in paise)
    amount_in_paise = int(order.total * 100)

    try:
        razorpay_order = razorpay_client.order.create({
            "amount": amount_in_paise,
            "currency": payment_data.currency,
            "receipt": order.order_number,
            "notes": {
                "order_id": str(order.id),
                "user_id": str(current_user.id)
            }
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Payment gateway error: {str(e)}")

    # Create payment record
    payment = Payment(
        razorpay_order_id=razorpay_order["id"],
        amount=order.total,
        currency=payment_data.currency,
        status="pending"
    )
    db.add(payment)
    db.flush()  # payment.id is only assigned on flush; linking before it stored NULL

    # Link payment to order
    order.payment_id = payment.id

    db.commit()

    return RazorpayOrderResponse(
        razorpay_order_id=razorpay_order["id"],
        amount=amount_in_paise,
        currency=payment_data.currency,
        key_id=settings.RAZORPAY_KEY_ID
    )


@router.post("/verify", response_model=PaymentResponse)
def verify_payment(
    verification_data: PaymentVerify,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Get payment record
    payment = db.query(Payment).filter(
        Payment.razorpay_order_id == verification_data.razorpay_order_id
    ).first()

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    order = order_for_payment(db, payment)
    if not order or order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Verify signature
    message = f"{verification_data.razorpay_order_id}|{verification_data.razorpay_payment_id}"
    expected_signature = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, verification_data.razorpay_signature):
        payment.status = "failed"
        payment.error_description = "Invalid signature"
        db.commit()
        raise HTTPException(status_code=400, detail="Payment verification failed")

    # Update payment record
    payment.razorpay_payment_id = verification_data.razorpay_payment_id
    payment.razorpay_signature = verification_data.razorpay_signature
    payment.status = "completed"

    # Get payment details from Razorpay
    try:
        rz_payment = razorpay_client.payment.fetch(verification_data.razorpay_payment_id)
        payment.method = rz_payment.get("method")
    except Exception:
        pass

    # Update order status
    newly_confirmed = order.status == OrderStatus.PENDING.value
    order.status = OrderStatus.CONFIRMED.value

    db.commit()
    db.refresh(payment)

    if newly_confirmed:
        background_tasks.add_task(push_order_in_background, order.id)

    return payment


@router.get("/{payment_id}", response_model=PaymentResponse)
def get_payment(
    payment_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    # Verify ownership through order
    order = db.query(Order).filter(Order.payment_id == payment_id).first()
    if order and order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    return payment


@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_razorpay_signature: str = Header(...),
    db: Session = Depends(get_db),
):
    """
    Handle Razorpay webhooks for async payment updates.

    Edge cases handled:
    1. Payment success: Confirm order
    2. Payment failure: Restore stock so others can buy
    """
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Payment webhook is not configured")

    raw_payload = await request.body()
    expected_signature = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode(), raw_payload, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected_signature, x_razorpay_signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid webhook payload")

    event = payload.get("event")

    if event == "payment.captured":
        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        razorpay_order_id = payment_entity.get("order_id")

        payment = db.query(Payment).filter(
            Payment.razorpay_order_id == razorpay_order_id
        ).first()

        if payment and payment.status != "completed":
            payment.razorpay_payment_id = payment_entity.get("id")
            payment.status = "completed"
            payment.method = payment_entity.get("method")

            order = order_for_payment(db, payment)
            newly_confirmed = bool(order) and order.status == OrderStatus.PENDING.value
            if order:
                order.status = OrderStatus.CONFIRMED.value
                # Stock stays reserved - it's now sold

            db.commit()

            if newly_confirmed:
                background_tasks.add_task(push_order_in_background, order.id)

    elif event == "payment.failed":
        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        razorpay_order_id = payment_entity.get("order_id")

        payment = db.query(Payment).filter(
            Payment.razorpay_order_id == razorpay_order_id
        ).first()

        if payment:
            payment.status = "failed"
            payment.error_code = payment_entity.get("error_code")
            payment.error_description = payment_entity.get("error_description")

            # EDGE CASE: Restore stock on payment failure
            order = order_for_payment(db, payment, lock=True)

            if order and order.status == OrderStatus.PENDING.value:
                restore_order_stock(order, db)
                order.status = OrderStatus.CANCELLED.value

            db.commit()

    return {"status": "ok"}
