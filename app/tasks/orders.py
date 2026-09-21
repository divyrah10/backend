from datetime import datetime, timedelta
from app.core.celery_app import celery_app
from app.core.cache import CacheInvalidator
from app.db.session import SessionLocal
from app.models.cart import CartItem
from app.models.order import Order
from app.models.product import Product
from app.tasks.email import send_order_confirmation, send_shipping_notification
import logging

logger = logging.getLogger(__name__)


@celery_app.task
def process_order_confirmation(order_id: str):
    """Process order after successful payment"""
    db = SessionLocal()
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            logger.error(f"Order {order_id} not found")
            return {"success": False, "error": "Order not found"}

        # Send confirmation email
        send_order_confirmation.delay(
            order_id=str(order.id),
            email=order.user.email
        )

        # Clear user's cart
        db.query(CartItem).filter(CartItem.user_id == order.user_id).delete()
        db.commit()

        # Invalidate cart cache
        CacheInvalidator.invalidate_cart(user_id=str(order.user_id))

        logger.info(f"Order {order_id} processed successfully")

        return {"success": True, "order_id": order_id}
    finally:
        db.close()


@celery_app.task
def cleanup_abandoned_carts():
    """Clean up abandoned guest carts older than 7 days"""
    db = SessionLocal()
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=7)

        # Delete old guest cart items (carts without user_id)
        deleted = db.query(CartItem).filter(
            CartItem.user_id == None,
            CartItem.created_at < cutoff_date
        ).delete()

        db.commit()

        logger.info(f"Cleaned up {deleted} abandoned cart items")

        return {"deleted_items": deleted}
    finally:
        db.close()


@celery_app.task
def release_expired_orders(max_age_minutes: int = 30):
    """Cancel unpaid orders and safely return their reserved inventory."""
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)
        orders = db.query(Order).filter(
            Order.status == "pending",
            Order.stock_reserved == "yes",
            Order.created_at < cutoff,
        ).with_for_update().all()

        released = 0
        for order in orders:
            product_ids = [item.product_id for item in order.items]
            products = db.query(Product).filter(Product.id.in_(product_ids)).order_by(Product.id).with_for_update().all()
            product_map = {str(product.id): product for product in products}
            for item in order.items:
                product = product_map.get(str(item.product_id))
                if product:
                    product.stock_quantity += item.quantity
                    CacheInvalidator.invalidate_product(str(product.id), product.slug)
            order.stock_reserved = "restored"
            order.status = "cancelled"
            released += 1

        db.commit()
        return {"released_orders": released}
    finally:
        db.close()


@celery_app.task
def process_order_shipment(order_id: str, tracking_number: str):
    """Process order shipment and send notification"""
    db = SessionLocal()
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            logger.error(f"Order {order_id} not found")
            return {"success": False, "error": "Order not found"}

        # Update order status
        order.status = "shipped"
        db.commit()

        # Send shipping notification
        send_shipping_notification.delay(
            order_id=str(order.id),
            email=order.user.email,
            tracking_number=tracking_number
        )

        logger.info(f"Order {order_id} shipped with tracking {tracking_number}")

        return {"success": True, "order_id": order_id, "tracking_number": tracking_number}
    finally:
        db.close()


@celery_app.task
def generate_daily_sales_report():
    """Generate daily sales report"""
    db = SessionLocal()
    try:
        today = datetime.utcnow().date()
        yesterday = today - timedelta(days=1)

        # Get orders from yesterday
        orders = db.query(Order).filter(
            Order.created_at >= yesterday,
            Order.created_at < today,
            Order.status.in_(["confirmed", "processing", "shipped", "delivered"])
        ).all()

        total_revenue = sum(order.total for order in orders)
        total_orders = len(orders)
        total_items = sum(len(order.items) for order in orders)

        report = {
            "date": str(yesterday),
            "total_orders": total_orders,
            "total_revenue": float(total_revenue),
            "total_items_sold": total_items,
            "average_order_value": float(total_revenue / total_orders) if total_orders > 0 else 0
        }

        logger.info(f"Daily sales report for {yesterday}: {report}")

        # TODO: Store report or send to admins

        return report
    finally:
        db.close()
