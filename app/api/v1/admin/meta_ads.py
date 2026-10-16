from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.config import settings
from app.core.permissions import Permission
from app.db.session import get_db
from app.models.order import Order, OrderStatus
from app.models.user import User
from app.services.meta import (
    DATE_PRESETS,
    MetaClient,
    MetaError,
    ads_report,
    build_purchase_event,
    build_user_data,
    load_order,
)

router = APIRouter()


class TestEventRequest(BaseModel):
    test_event_code: str
    order_number: Optional[str] = None  # Defaults to the latest paid order


@router.get("/status")
def meta_status(current_user: User = Depends(require_permission(Permission.VIEW_REPORTS))):
    feed_url = f"{settings.API_V1_PREFIX}/meta/catalog.csv"
    return {
        "graph_version": settings.META_GRAPH_VERSION,
        "pixel_id": settings.META_PIXEL_ID or None,
        "conversions_api": settings.meta_capi_enabled,
        "test_mode": bool(settings.META_TEST_EVENT_CODE),
        "insights": settings.meta_insights_enabled,
        "catalog_feed_path": feed_url + ("?token=…" if settings.META_CATALOG_FEED_TOKEN else ""),
    }


@router.get("/insights")
def meta_insights(
    date_preset: str = Query(default="last_7d"),
    current_user: User = Depends(require_permission(Permission.VIEW_REPORTS)),
):
    if not settings.meta_insights_enabled:
        raise HTTPException(status_code=503, detail="Set META_AD_ACCOUNT_ID and META_ADS_ACCESS_TOKEN to see ad performance")
    if date_preset not in DATE_PRESETS:
        raise HTTPException(status_code=400, detail=f"date_preset must be one of {sorted(DATE_PRESETS)}")
    try:
        return ads_report(date_preset)
    except MetaError as error:
        raise HTTPException(status_code=502, detail=str(error))


@router.post("/test-event")
def meta_test_event(
    body: TestEventRequest,
    current_user: User = Depends(require_permission(Permission.MANAGE_SETTINGS)),
    db: Session = Depends(get_db),
):
    """Resend a paid order's Purchase under a test code, to check setup in Events Manager > Test events."""
    if not settings.meta_capi_enabled:
        raise HTTPException(status_code=503, detail="Set META_PIXEL_ID and META_CAPI_ACCESS_TOKEN first")
    query = db.query(Order.id).filter(Order.status != OrderStatus.PENDING.value, Order.status != OrderStatus.CANCELLED.value)
    if body.order_number:
        query = query.filter(Order.order_number == body.order_number)
    order_id = query.order_by(Order.created_at.desc()).limit(1).scalar()
    order = load_order(db, order_id) if order_id else None
    if not order:
        raise HTTPException(status_code=404, detail="No paid order to send")

    try:
        result = MetaClient().send_events(
            [build_purchase_event(order, build_user_data(order))], test_event_code=body.test_event_code,
        )
    except MetaError as error:
        raise HTTPException(status_code=502, detail=str(error))
    return {"order_number": order.order_number, **result}
