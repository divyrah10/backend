from datetime import datetime, timedelta
from app.core.celery_app import celery_app
from app.core.cache import CacheInvalidator
from app.db.session import SessionLocal
from app.models.cart import CartItem
from app.models.order import Order
from app.tasks.email import send_order_confirmation, send_shipping_notification
from app.tasks.inventory import bulk_update_stock
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

        # Update stock for ordered items
        stock_updates = []
        for item in order.items:
            stock_updates.append({
                "product_id": str(item.product_id),
                "quantity_change": -item.quantity
            })

        if stock_updates:
            bulk_update_stock.delay(stock_updates)

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
        order.tracking_number = tracking_number
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
            Order.payment_status == "paid"
        ).all()

        total_revenue = sum(order.total_amount for order in orders)
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
