from app.core.celery_app import celery_app
from app.core.cache import cache, CacheInvalidator
from app.db.session import SessionLocal
from app.models.product import Product
from app.tasks.email import send_low_stock_alert
import logging

logger = logging.getLogger(__name__)


@celery_app.task
def check_low_stock():
    """Check for products with low stock and send alerts"""
    db = SessionLocal()
    try:
        low_stock_products = db.query(Product).filter(
            Product.is_active == True,
            Product.stock_quantity <= Product.low_stock_threshold,
            Product.stock_quantity > 0
        ).all()

        if low_stock_products:
            logger.info(f"Found {len(low_stock_products)} products with low stock")

            for product in low_stock_products:
                # Queue email alert for each low stock product
                send_low_stock_alert.delay(
                    product_name=product.name,
                    current_stock=product.stock_quantity,
                    admin_emails=["admin@notjustdark.com"]  # TODO: Get from settings
                )

        out_of_stock = db.query(Product).filter(
            Product.is_active == True,
            Product.stock_quantity == 0
        ).count()

        logger.info(f"Low stock check complete. Low: {len(low_stock_products)}, Out of stock: {out_of_stock}")

        return {
            "low_stock_count": len(low_stock_products),
            "out_of_stock_count": out_of_stock
        }
    finally:
        db.close()


@celery_app.task
def sync_inventory_cache():
    """Sync inventory data to cache for fast lookups"""
    db = SessionLocal()
    try:
        # Get stock levels for all active products
        products = db.query(Product.id, Product.stock_quantity).filter(
            Product.is_active == True
        ).all()

        stock_data = {str(p.id): p.stock_quantity for p in products}

        # Store in cache with 10 minute TTL
        cache.set("inventory:stock_levels", stock_data, ttl=600)

        logger.info(f"Synced inventory cache for {len(products)} products")

        return {"synced_products": len(products)}
    finally:
        db.close()


@celery_app.task
def update_stock(product_id: str, quantity_change: int, reason: str = ""):
    """Update product stock (used for bulk operations)"""
    db = SessionLocal()
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            logger.error(f"Product {product_id} not found for stock update")
            return {"success": False, "error": "Product not found"}

        old_stock = product.stock_quantity
        new_stock = max(0, old_stock + quantity_change)
        product.stock_quantity = new_stock

        db.commit()

        # Invalidate cache
        CacheInvalidator.invalidate_product(product_id, product.slug)

        logger.info(f"Updated stock for {product.name}: {old_stock} -> {new_stock} ({reason})")

        # Check if now low stock
        if new_stock <= product.low_stock_threshold and new_stock > 0:
            send_low_stock_alert.delay(
                product_name=product.name,
                current_stock=new_stock,
                admin_emails=["admin@notjustdark.com"]
            )

        return {
            "success": True,
            "product_id": product_id,
            "old_stock": old_stock,
            "new_stock": new_stock
        }
    finally:
        db.close()


@celery_app.task
def bulk_update_stock(updates: list):
    """
    Bulk update stock for multiple products

    Args:
        updates: List of dicts with product_id and quantity_change
                 e.g., [{"product_id": "uuid", "quantity_change": -1}, ...]
    """
    db = SessionLocal()
    try:
        results = []
        for update in updates:
            product_id = update.get("product_id")
            quantity_change = update.get("quantity_change", 0)

            product = db.query(Product).filter(Product.id == product_id).first()
            if product:
                old_stock = product.stock_quantity
                new_stock = max(0, old_stock + quantity_change)
                product.stock_quantity = new_stock
                results.append({
                    "product_id": product_id,
                    "success": True,
                    "old_stock": old_stock,
                    "new_stock": new_stock
                })
            else:
                results.append({
                    "product_id": product_id,
                    "success": False,
                    "error": "Product not found"
                })

        db.commit()

        # Invalidate all product caches after bulk update
        CacheInvalidator.invalidate_all_products()

        logger.info(f"Bulk stock update completed for {len(updates)} products")

        return {"results": results, "total": len(updates)}
    finally:
        db.close()
