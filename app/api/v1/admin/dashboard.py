from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from decimal import Decimal
from app.db.session import get_db
from app.api.deps import require_permission
from app.core.permissions import Permission
from app.models.order import Order, OrderStatus
from app.models.product import Product
from app.models.user import User
from app.models.review import Review

router = APIRouter()


@router.get("/stats")
def get_dashboard_stats(
    current_user: User = Depends(require_permission(Permission.VIEW_DASHBOARD)),
    db: Session = Depends(get_db)
):
    today = datetime.utcnow().date()
    thirty_days_ago = today - timedelta(days=30)

    # Total revenue (completed orders)
    total_revenue = db.query(func.sum(Order.total)).filter(
        Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.SHIPPED.value, OrderStatus.DELIVERED.value])
    ).scalar() or Decimal("0")

    # Revenue this month
    monthly_revenue = db.query(func.sum(Order.total)).filter(
        Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.SHIPPED.value, OrderStatus.DELIVERED.value]),
        func.date(Order.created_at) >= thirty_days_ago
    ).scalar() or Decimal("0")

    # Total orders
    total_orders = db.query(func.count(Order.id)).scalar()

    # Orders this month
    monthly_orders = db.query(func.count(Order.id)).filter(
        func.date(Order.created_at) >= thirty_days_ago
    ).scalar()

    # Pending orders
    pending_orders = db.query(func.count(Order.id)).filter(
        Order.status == OrderStatus.PENDING.value
    ).scalar()

    # Total customers
    from app.core.permissions import RoleName
    from app.models.role import Role
    customer_role = db.query(Role).filter(Role.name == RoleName.CUSTOMER.value).first()
    total_customers = 0
    if customer_role:
        total_customers = db.query(func.count(User.id)).filter(
            User.role_id == customer_role.id
        ).scalar()

    # Total products
    total_products = db.query(func.count(Product.id)).filter(Product.is_active == True).scalar()

    # Low stock products
    low_stock = db.query(func.count(Product.id)).filter(
        Product.is_active == True,
        Product.stock_quantity <= Product.low_stock_threshold
    ).scalar()

    # Pending reviews
    pending_reviews = db.query(func.count(Review.id)).filter(Review.is_approved == False).scalar()

    return {
        "revenue": {
            "total": float(total_revenue),
            "monthly": float(monthly_revenue)
        },
        "orders": {
            "total": total_orders,
            "monthly": monthly_orders,
            "pending": pending_orders
        },
        "customers": {
            "total": total_customers
        },
        "products": {
            "total": total_products,
            "low_stock": low_stock
        },
        "reviews": {
            "pending": pending_reviews
        }
    }


@router.get("/recent-orders")
def get_recent_orders(
    limit: int = 10,
    current_user: User = Depends(require_permission(Permission.VIEW_DASHBOARD)),
    db: Session = Depends(get_db)
):
    orders = db.query(Order).order_by(Order.created_at.desc()).limit(limit).all()

    return [{
        "id": str(order.id),
        "order_number": order.order_number,
        "customer_name": order.shipping_address.get("full_name", "N/A"),
        "total": float(order.total),
        "status": order.status,
        "created_at": order.created_at.isoformat()
    } for order in orders]


@router.get("/sales-chart")
def get_sales_chart_data(
    days: int = 30,
    current_user: User = Depends(require_permission(Permission.VIEW_REPORTS)),
    db: Session = Depends(get_db)
):
    today = datetime.utcnow().date()
    start_date = today - timedelta(days=days)

    # Get daily sales
    sales_data = db.query(
        func.date(Order.created_at).label("date"),
        func.sum(Order.total).label("revenue"),
        func.count(Order.id).label("orders")
    ).filter(
        Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.SHIPPED.value, OrderStatus.DELIVERED.value]),
        func.date(Order.created_at) >= start_date
    ).group_by(func.date(Order.created_at)).all()

    # Fill in missing dates
    result = []
    current_date = start_date
    sales_dict = {str(s.date): {"revenue": float(s.revenue), "orders": s.orders} for s in sales_data}

    while current_date <= today:
        date_str = str(current_date)
        if date_str in sales_dict:
            result.append({
                "date": date_str,
                "revenue": sales_dict[date_str]["revenue"],
                "orders": sales_dict[date_str]["orders"]
            })
        else:
            result.append({
                "date": date_str,
                "revenue": 0,
                "orders": 0
            })
        current_date += timedelta(days=1)

    return result


@router.get("/top-products")
def get_top_products(
    limit: int = 5,
    current_user: User = Depends(require_permission(Permission.VIEW_REPORTS)),
    db: Session = Depends(get_db)
):
    from app.models.order import OrderItem

    top_products = db.query(
        Product.id,
        Product.name,
        Product.images,
        func.sum(OrderItem.quantity).label("total_sold"),
        func.sum(OrderItem.subtotal).label("total_revenue")
    ).join(OrderItem, OrderItem.product_id == Product.id).join(
        Order, Order.id == OrderItem.order_id
    ).filter(
        Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.SHIPPED.value, OrderStatus.DELIVERED.value])
    ).group_by(Product.id).order_by(func.sum(OrderItem.quantity).desc()).limit(limit).all()

    return [{
        "id": str(p.id),
        "name": p.name,
        "image": p.images[0] if p.images else None,
        "total_sold": p.total_sold,
        "total_revenue": float(p.total_revenue)
    } for p in top_products]
