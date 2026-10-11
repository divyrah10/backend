"""Shiprocket integration: push paid orders, and fold tracking updates back into shipments.

API reference: https://apidocs.shiprocket.in
"""
import logging
import re
import threading
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

import httpx
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.pricing import GST_RATE
from app.db.session import SessionLocal
from app.models.order import Order, OrderStatus, Shipment, TrackingEvent

logger = logging.getLogger(__name__)

PROVIDER = "shiprocket"
TRACKING_URL = "https://shiprocket.co/tracking/{awb}"
# Shiprocket tokens last 10 days; refresh a day early.
TOKEN_TTL = timedelta(days=9)

# Ordered most-specific first: "RTO DELIVERED" must win over "DELIVERED".
_STATUS_RULES = [
    ("RTO DELIVERED", "rto_delivered"),
    ("RTO", "rto_in_transit"),
    ("OUT FOR DELIVERY", "out_for_delivery"),
    ("UNDELIVERED", "ndr"),
    ("NDR", "ndr"),
    ("DELIVERED", "delivered"),
    ("CANCEL", "cancelled"),
    ("LOST", "cancelled"),
    ("OUT FOR PICKUP", "ready_to_ship"),
    ("PICKUP EXCEPTION", "delivery_delayed"),
    ("PICKED UP", "picked_up"),
    ("SHIPPED", "in_transit"),
    ("IN TRANSIT", "in_transit"),
    ("REACHED", "in_transit"),
    ("DELAY", "delivery_delayed"),
    ("MISROUTED", "delivery_delayed"),
    ("PICKUP", "ready_to_ship"),
    ("AWB ASSIGNED", "ready_to_ship"),
    ("READY TO SHIP", "ready_to_ship"),
    ("MANIFEST", "ready_to_ship"),
]

STATUS_TITLES = {
    "processing": "Preparing your order",
    "ready_to_ship": "Ready to ship",
    "picked_up": "Picked up by courier",
    "in_transit": "In transit",
    "out_for_delivery": "Out for delivery",
    "delivered": "Delivered",
    "delivery_delayed": "Delivery delayed",
    "ndr": "Delivery attempted",
    "rto_in_transit": "Returning to sender",
    "rto_delivered": "Returned to sender",
    "cancelled": "Shipment cancelled",
}


class ShiprocketError(Exception):
    pass


def describe_error(body: Any) -> str:
    """Shiprocket's reason, field by field. 422s put the useful part in "errors":
    {"message": "The given data was invalid.", "errors": {"billing_phone": ["..."]}}.
    """
    if not isinstance(body, dict):
        return ""
    parts = [str(body["message"])] if body.get("message") else []
    errors = body.get("errors")
    if isinstance(errors, dict):
        for field, problems in errors.items():
            text = "; ".join(map(str, problems)) if isinstance(problems, list) else str(problems)
            parts.append(f"{field}: {text}")
    elif errors:
        parts.append(str(errors))
    return " | ".join(parts)[:500]


def map_status(label: Optional[str]) -> Optional[str]:
    """Translate a Shiprocket status label into one of our shipment statuses."""
    if not label:
        return None
    normalized = re.sub(r"[_\-]+", " ", label).upper().strip()
    if normalized == "NEW":
        return "processing"
    for needle, status in _STATUS_RULES:
        if needle in normalized:
            return status
    return None


def normalize_phone(phone: Optional[str]) -> str:
    digits = re.sub(r"\D", "", phone or "")
    return digits[-10:]


def first_mobile(*candidates: Optional[str]) -> str:
    """First candidate that is really a 10-digit number. Old addresses allowed free text,
    so a phone field can hold a name; that must fall through to the next source."""
    for candidate in candidates:
        phone = normalize_phone(candidate)
        if len(phone) == 10:
            return phone
    return ""


def parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d %m %Y %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def build_order_payload(order: Order, fallback_phone: Optional[str] = None) -> dict[str, Any]:
    """Shape an order as Shiprocket's /orders/create/adhoc body. Prices are GST-inclusive."""
    address = order.shipping_address or {}
    full_name = (address.get("full_name") or order.user.full_name or "").strip()
    first_name, _, last_name = full_name.partition(" ")
    units = sum(item.quantity for item in order.items)

    items = []
    for item in order.items:
        size = (item.attributes or {}).get("size")
        sku = getattr(item.product, "sku", None) or str(item.product_id)
        items.append({
            "name": f"{item.product_name} ({size})" if size else item.product_name,
            "sku": f"{sku}-{size}" if size else sku,
            "units": item.quantity,
            "selling_price": float(item.unit_price),
            "discount": 0,
            "tax": float(GST_RATE * 100),
        })

    return {
        "order_id": order.order_number,
        "order_date": (order.created_at or datetime.utcnow()).strftime("%Y-%m-%d %H:%M"),
        "pickup_location": settings.SHIPROCKET_PICKUP_LOCATION,
        "billing_customer_name": first_name,
        "billing_last_name": last_name,
        "billing_address": address.get("address_line1", ""),
        "billing_address_2": address.get("address_line2") or "",
        "billing_city": address.get("city", ""),
        "billing_pincode": address.get("postal_code", ""),
        "billing_state": address.get("state", ""),
        "billing_country": address.get("country") or "India",
        "billing_email": order.user.email,
        "billing_phone": first_mobile(address.get("phone"), order.user.phone, fallback_phone),
        "shipping_is_billing": True,
        "order_items": items,
        "payment_method": "Prepaid",
        "shipping_charges": float(order.shipping_cost or 0),
        "total_discount": float(order.discount or 0),
        "sub_total": float(order.total),
        "length": settings.SHIPROCKET_PACKAGE_LENGTH_CM,
        "breadth": settings.SHIPROCKET_PACKAGE_BREADTH_CM,
        "height": settings.SHIPROCKET_PACKAGE_HEIGHT_CM,
        "weight": round(max(units, 1) * settings.SHIPROCKET_ITEM_WEIGHT_KG, 2),
    }


class ShiprocketClient:
    _token: Optional[str] = None
    _token_expires_at: datetime = datetime.min
    _lock = threading.Lock()

    def __init__(self, http: Optional[httpx.Client] = None):
        self._http = http or httpx.Client(base_url=settings.SHIPROCKET_BASE_URL, timeout=20)

    def _login(self) -> str:
        cls = type(self)
        with cls._lock:
            if cls._token and datetime.utcnow() < cls._token_expires_at:
                return cls._token
            response = self._http.post("/auth/login", json={
                "email": settings.SHIPROCKET_EMAIL,
                "password": settings.SHIPROCKET_PASSWORD,
            })
            if response.status_code != 200 or not response.json().get("token"):
                raise ShiprocketError(f"Shiprocket login failed ({response.status_code})")
            cls._token = response.json()["token"]
            cls._token_expires_at = datetime.utcnow() + TOKEN_TTL
            return cls._token

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        for attempt in range(2):
            headers = {"Authorization": f"Bearer {self._login()}"}
            response = self._http.request(method, path, headers=headers, **kwargs)
            if response.status_code == 401 and attempt == 0:
                type(self)._token = None  # Token revoked early; log in again once.
                continue
            break
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code >= 400:
            message = describe_error(body) or response.text[:300]
            logger.warning("Shiprocket %s failed (%s): %s", path, response.status_code, message)
            raise ShiprocketError(f"Shiprocket {path} failed ({response.status_code}): {message}")
        return body

    def create_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/orders/create/adhoc", json=payload)

    def assign_awb(self, shipment_id: str) -> dict[str, Any]:
        body = self._request("POST", "/courier/assign/awb", json={"shipment_id": shipment_id})
        if not body.get("awb_assign_status"):
            message = body.get("message") or body.get("response", {}).get("data", {}).get("awb_assign_error")
            raise ShiprocketError(f"AWB not assigned: {message}")
        return body.get("response", {}).get("data", {})

    def generate_pickup(self, shipment_id: str) -> dict[str, Any]:
        return self._request("POST", "/courier/generate/pickup", json={"shipment_id": [shipment_id]})

    def track_awb(self, awb: str) -> dict[str, Any]:
        return self._request("GET", f"/courier/track/awb/{awb}").get("tracking_data", {})

    def track_shipment(self, shipment_id: str) -> dict[str, Any]:
        """Tracking by Shiprocket shipment id; works before we know the AWB."""
        return self._request("GET", f"/courier/track/shipment/{shipment_id}").get("tracking_data", {})


def apply_status(order: Order, shipment: Shipment, status: str) -> None:
    """Set a shipment status and move the order along with it."""
    shipment.status = status
    shipment.last_synced_at = datetime.utcnow()
    if status in {"picked_up", "in_transit", "out_for_delivery"}:
        order.status = OrderStatus.SHIPPED.value
    elif status == "delivered":
        order.status = OrderStatus.DELIVERED.value


def record_event(
    db: Session,
    shipment: Shipment,
    status: str,
    title: str,
    occurred_at: datetime,
    description: Optional[str] = None,
    location: Optional[str] = None,
) -> bool:
    """Add a tracking event unless the same one is already stored. Returns True if added."""
    existing = {(e.title, e.occurred_at) for e in shipment.events}
    if (title, occurred_at) in existing:
        return False
    event = TrackingEvent(
        shipment_id=shipment.id,
        status=status,
        title=title,
        description=description,
        location=location,
        occurred_at=occurred_at,
    )
    db.add(event)
    shipment.events.append(event)
    return True


def load_order(db: Session, order_id) -> Optional[Order]:
    return db.query(Order).options(
        joinedload(Order.items),
        joinedload(Order.user),
        joinedload(Order.shipment).joinedload(Shipment.events),
    ).filter(Order.id == order_id).first()


def payment_contact(order: Order) -> Optional[str]:
    """The phone the customer gave Razorpay at payment, for orders whose address has none."""
    if first_mobile((order.shipping_address or {}).get("phone"), order.user.phone):
        return None
    payment = order.payment
    if not payment or not payment.razorpay_payment_id:
        return None
    from app.api.v1.payments import razorpay_client

    try:
        return razorpay_client.payment.fetch(payment.razorpay_payment_id).get("contact")
    except Exception:
        logger.warning("Could not fetch Razorpay contact for order %s", order.order_number)
        return None


def push_order(db: Session, order: Order, client: Optional[ShiprocketClient] = None) -> Shipment:
    """Create the order in Shiprocket (once) and store what comes back. Commits on success."""
    from app.api.v1.orders import get_or_create_shipment

    if not settings.shiprocket_enabled:
        raise ShiprocketError("Shiprocket is not configured")

    client = client or ShiprocketClient()
    shipment = get_or_create_shipment(db, order)
    shipment.provider = PROVIDER

    if not shipment.provider_shipment_id:
        if order.status not in {OrderStatus.CONFIRMED.value, OrderStatus.PROCESSING.value}:
            raise ShiprocketError(f"Order is {order.status}; only paid orders can be shipped")
        created = client.create_order(build_order_payload(order, fallback_phone=payment_contact(order)))
        if not created.get("shipment_id"):
            raise ShiprocketError(f"Shiprocket did not return a shipment: {created.get('message') or created}")
        shipment.provider_shipment_id = str(created["shipment_id"])
        if created.get("awb_code"):
            shipment.awb_code = created["awb_code"]
            shipment.courier_name = created.get("courier_name") or shipment.courier_name
        order.status = OrderStatus.PROCESSING.value
        apply_status(order, shipment, "processing")
        record_event(db, shipment, "processing", STATUS_TITLES["processing"], datetime.utcnow(),
                     description="Your order is being packed at our studio.")
        db.commit()

    newly_assigned = False
    if settings.SHIPROCKET_AUTO_ASSIGN_AWB and not shipment.awb_code:
        awb = client.assign_awb(shipment.provider_shipment_id)
        newly_assigned = True
        shipment.awb_code = awb.get("awb_code")
        shipment.courier_name = awb.get("courier_name") or shipment.courier_name
        db.commit()

    if shipment.awb_code:
        shipment.tracking_url = TRACKING_URL.format(awb=shipment.awb_code)
        if shipment.status == "processing":
            apply_status(order, shipment, "ready_to_ship")
            record_event(db, shipment, "ready_to_ship", STATUS_TITLES["ready_to_ship"], datetime.utcnow(),
                         description=f"Handed to {shipment.courier_name}." if shipment.courier_name else None)
        db.commit()

        # Only on first assignment, so retries don't book a second pickup.
        if settings.SHIPROCKET_AUTO_PICKUP and newly_assigned:
            client.generate_pickup(shipment.provider_shipment_id)

    return shipment


def push_order_in_background(order_id) -> None:
    """Background-task entry point: never raises, so a Shiprocket outage can't affect checkout."""
    if not settings.shiprocket_enabled:
        return
    db = SessionLocal()
    try:
        order = load_order(db, order_id)
        if order:
            push_order(db, order)
    except Exception:
        db.rollback()
        logger.exception("Shiprocket push failed for order %s; retry from admin", order_id)
    finally:
        db.close()


def apply_tracking_update(db: Session, payload: dict[str, Any], shipment: Optional[Shipment] = None) -> Optional[Shipment]:
    """Fold a Shiprocket tracking payload into a shipment (found by AWB or order if not given). Caller commits."""
    awb = str(payload.get("awb") or "").strip()
    query = db.query(Shipment).options(joinedload(Shipment.events), joinedload(Shipment.order))
    if not shipment and awb:
        shipment = query.filter(Shipment.awb_code == awb).first()
    if not shipment and payload.get("order_id"):
        # Shiprocket's order_id is ours: we send order_number as the channel order id.
        shipment = query.join(Order).filter(Order.order_number == str(payload["order_id"])).first()
    if not shipment:
        return None

    if awb and not shipment.awb_code:
        shipment.awb_code = awb
        if shipment.status in {"order_confirmed", "processing"}:
            apply_status(shipment.order, shipment, "ready_to_ship")
            record_event(db, shipment, "ready_to_ship", STATUS_TITLES["ready_to_ship"], datetime.utcnow(),
                         description=f"Handed to {payload['courier_name']}." if payload.get("courier_name") else None)
    if shipment.awb_code:
        shipment.tracking_url = TRACKING_URL.format(awb=shipment.awb_code)
    if payload.get("courier_name"):
        shipment.courier_name = payload["courier_name"]
    if etd := parse_timestamp(payload.get("etd")):
        shipment.estimated_delivery = etd

    for scan in payload.get("scans") or []:
        status = map_status(scan.get("sr-status-label") or scan.get("activity"))
        occurred_at = parse_timestamp(scan.get("date"))
        if not status or not occurred_at:
            continue
        record_event(
            db, shipment, status,
            title=STATUS_TITLES.get(status, status.replace("_", " ").title()),
            description=scan.get("activity"),
            location=scan.get("location"),
            occurred_at=occurred_at,
        )

    status = map_status(payload.get("shipment_status") or payload.get("current_status"))
    if status:
        apply_status(shipment.order, shipment, status)
    return shipment


def refresh_tracking(db: Session, order: Order, client: Optional[ShiprocketClient] = None) -> Shipment:
    """Pull the latest tracking from Shiprocket and store it. Commits.

    Looks up by AWB when we have one, otherwise by Shiprocket shipment id, so the
    AWB and courier assigned in the Shiprocket panel come back without a webhook.
    """
    shipment = order.shipment
    if not shipment or not (shipment.awb_code or shipment.provider_shipment_id):
        raise ShiprocketError("This order hasn't been sent to Shiprocket yet")

    client = client or ShiprocketClient()
    data = (client.track_awb(shipment.awb_code) if shipment.awb_code
            else client.track_shipment(shipment.provider_shipment_id))
    track = (data.get("shipment_track") or [{}])[0] or {}
    awb = str(track.get("awb_code") or track.get("awb") or "").strip()
    if not shipment.awb_code and not awb:
        raise ShiprocketError("Shiprocket hasn't assigned a courier yet. Use Ship Now in Shiprocket, then refresh.")

    apply_tracking_update(db, {
        "awb": shipment.awb_code or awb,
        "courier_name": track.get("courier_name") or track.get("courier_company_name"),
        "current_status": track.get("current_status"),
        "etd": track.get("edd") or data.get("etd"),
        "scans": data.get("shipment_track_activities") or [],
    }, shipment=shipment)
    db.commit()
    return shipment
