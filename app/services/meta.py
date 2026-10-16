"""Meta (Facebook/Instagram) ads: Conversions API events, the catalog feed, and ad insights.

API references:
- Conversions API: https://developers.facebook.com/docs/marketing-api/conversions-api
- Catalog feed fields: https://developers.facebook.com/docs/marketing-api/catalog/reference
- Insights: https://developers.facebook.com/docs/marketing-api/insights
"""
import csv
import hashlib
import io
import logging
import re
import time
from decimal import Decimal
from typing import Any, Iterable, Optional

import httpx
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.order import Order
from app.models.product import Product
from app.services import inventory

logger = logging.getLogger(__name__)

# Meta reports purchases under several action types; the first present wins.
PURCHASE_ACTIONS = ("omni_purchase", "purchase", "offsite_conversion.fb_pixel_purchase")
INSIGHT_FIELDS = "spend,impressions,reach,clicks,ctr,cpc,cpm,actions,action_values"
DATE_PRESETS = {"today", "yesterday", "last_7d", "last_14d", "last_30d", "last_90d", "this_month", "last_month"}

FEED_COLUMNS = [
    "id", "item_group_id", "title", "description", "availability", "condition", "price",
    "sale_price", "link", "image_link", "additional_image_link", "brand", "size", "product_type",
]


class MetaError(Exception):
    pass


# --- Shared ids -------------------------------------------------------------
# Pixel, Conversions API and catalog must use the same content ids, or ads
# can't tie a purchase back to the product that was advertised.

def group_id(product) -> str:
    return getattr(product, "sku", None) or str(product.id)


def content_id(product, size: Optional[str] = None) -> str:
    return f"{group_id(product)}-{size}" if size else group_id(product)


def money(amount) -> str:
    return f"{Decimal(amount or 0):.2f} {settings.META_CATALOG_CURRENCY}"


# --- Customer information ---------------------------------------------------

def sha256(value: Optional[str]) -> Optional[str]:
    return hashlib.sha256(value.encode()).hexdigest() if value else None


def normalize_phone(phone: Optional[str], country_code: str = "91") -> Optional[str]:
    """Digits with the country code, as Meta matches them: "98765 43210" -> "919876543210"."""
    digits = re.sub(r"\D", "", phone or "").lstrip("0")
    if len(digits) == 10:
        digits = country_code + digits
    return digits if len(digits) >= 11 else None


def normalize_text(value: Optional[str]) -> Optional[str]:
    """Lowercase letters only, the format Meta expects for names, city and state."""
    cleaned = re.sub(r"[^a-z]", "", (value or "").lower())
    return cleaned or None


def build_user_data(
    order: Order,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    fbp: Optional[str] = None,
    fbc: Optional[str] = None,
) -> dict[str, Any]:
    """Hashed customer details for matching. Meta needs SHA-256 of normalised values;
    IP, user agent and the _fbp/_fbc cookies are sent as they are."""
    address = order.shipping_address or {}
    full_name = (address.get("full_name") or order.user.full_name or "").strip()
    first_name, _, last_name = full_name.partition(" ")
    postal_code = re.sub(r"\s", "", address.get("postal_code") or "").lower()

    hashed = {
        "em": sha256((order.user.email or "").strip().lower()),
        "ph": sha256(normalize_phone(address.get("phone")) or normalize_phone(order.user.phone)),
        "fn": sha256(normalize_text(first_name)),
        "ln": sha256(normalize_text(last_name)),
        "ct": sha256(normalize_text(address.get("city"))),
        "st": sha256(normalize_text(address.get("state"))),
        "zp": sha256(postal_code or None),
        "country": sha256("in" if (address.get("country") or "India").lower() == "india"
                          else normalize_text(address.get("country"))),
        "external_id": sha256(str(order.user_id)),
    }
    user_data = {key: [value] for key, value in hashed.items() if value}
    for key, value in (("client_ip_address", client_ip), ("client_user_agent", user_agent),
                       ("fbp", fbp), ("fbc", fbc)):
        if value:
            user_data[key] = value
    return user_data


def build_purchase_event(order: Order, user_data: dict[str, Any], event_source_url: Optional[str] = None) -> dict[str, Any]:
    """A Purchase server event. event_id is the order number, which the browser
    pixel sends too, so Meta counts the purchase once."""
    contents = []
    for item in order.items:
        size = inventory.item_size(item.attributes)
        contents.append({
            "id": content_id(item.product, size),
            "quantity": item.quantity,
            "item_price": float(item.unit_price),
        })
    created = order.created_at.timestamp() if order.created_at else time.time()
    return {
        "event_name": "Purchase",
        # Meta rejects events older than 7 days; a late webhook still counts as now.
        "event_time": int(max(created, time.time() - 6 * 86400)),
        "event_id": order.order_number,
        "action_source": "website",
        "event_source_url": event_source_url or f"{settings.STOREFRONT_URL}/checkout",
        "user_data": user_data,
        "custom_data": {
            "currency": settings.META_CATALOG_CURRENCY,
            "value": float(order.total),
            "order_id": order.order_number,
            "content_type": "product",
            "contents": contents,
            "content_ids": [c["id"] for c in contents],
            "num_items": sum(item.quantity for item in order.items),
        },
    }


# --- Graph API client --------------------------------------------------------

def ad_account_path() -> str:
    account = settings.META_AD_ACCOUNT_ID.strip()
    return account if account.startswith("act_") else f"act_{account}"


class MetaClient:
    def __init__(self, http: Optional[httpx.Client] = None):
        self._http = http or httpx.Client(
            base_url=f"{settings.META_GRAPH_URL}/{settings.META_GRAPH_VERSION}", timeout=20,
        )

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        response = self._http.request(method, path, **kwargs)
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code >= 400 or "error" in body:
            error = body.get("error") or {}
            message = error.get("error_user_msg") or error.get("message") or response.text[:300]
            logger.warning("Meta %s failed (%s): %s", path, response.status_code, message)
            raise MetaError(f"Meta {path} failed ({response.status_code}): {message}")
        return body

    def send_events(self, events: list[dict[str, Any]], test_event_code: Optional[str] = None) -> dict[str, Any]:
        """POST /{pixel_id}/events. Returns {"events_received": n, "fbtrace_id": ...}."""
        payload: dict[str, Any] = {"data": events, "access_token": settings.META_CAPI_ACCESS_TOKEN}
        code = test_event_code or settings.META_TEST_EVENT_CODE
        if code:
            payload["test_event_code"] = code
        return self._request("POST", f"/{settings.META_PIXEL_ID}/events", json=payload)

    def insights(self, date_preset: str, level: str = "account", daily: bool = False) -> list[dict[str, Any]]:
        params = {
            "access_token": settings.META_ADS_ACCESS_TOKEN,
            "date_preset": date_preset,
            "level": level,
            "fields": INSIGHT_FIELDS + (",campaign_id,campaign_name" if level == "campaign" else ""),
            "limit": 100,
        }
        if daily:
            params["time_increment"] = 1
        return self._request("GET", f"/{ad_account_path()}/insights", params=params).get("data", [])


# --- Conversions API ---------------------------------------------------------

def load_order(db: Session, order_id) -> Optional[Order]:
    return db.query(Order).options(
        joinedload(Order.items),
        joinedload(Order.user),
    ).filter(Order.id == order_id).first()


def send_purchase(order: Order, client: Optional[MetaClient] = None, **context) -> dict[str, Any]:
    event_source_url = context.pop("event_source_url", None)
    event = build_purchase_event(order, build_user_data(order, **context), event_source_url)
    return (client or MetaClient()).send_events([event])


def send_purchase_in_background(order_id, **context) -> None:
    """Background-task entry point: never raises, so a Meta outage can't affect checkout."""
    if not settings.meta_capi_enabled:
        return
    db = SessionLocal()
    try:
        order = load_order(db, order_id)
        if order:
            send_purchase(order, **context)
    except Exception:
        logger.exception("Meta Purchase event failed for order %s", order_id)
    finally:
        db.close()


# --- Catalog feed ------------------------------------------------------------

def plain_text(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()


def feed_rows(products: Iterable[Product]) -> list[dict[str, str]]:
    """One row per size (grouped by item_group_id), or one row for unsized products."""
    rows = []
    for product in products:
        images = [url for url in (product.images or []) if url]
        if not images:
            continue  # Meta rejects items without an image.
        on_sale = product.is_on_sale
        base = {
            "item_group_id": group_id(product),
            "title": product.name[:200],
            "description": (plain_text(product.description) or product.short_description or product.name)[:9999],
            "condition": "new",
            "price": money(product.compare_at_price if on_sale else product.price),
            "sale_price": money(product.price) if on_sale else "",
            "link": f"{settings.STOREFRONT_URL}/products/{product.slug}",
            "image_link": images[0],
            "additional_image_link": ",".join(images[1:11]),
            "brand": settings.APP_NAME,
            "product_type": product.category.name if product.category else "",
        }
        sizes = inventory.product_sizes(product)
        for size in sizes or [None]:
            stock = inventory.available(product, size) if size else product.stock_quantity
            rows.append({
                **base,
                "id": content_id(product, size),
                "size": size or "",
                "availability": "in stock" if stock > 0 else "out of stock",
            })
    return rows


def catalog_csv(db: Session) -> str:
    products = db.query(Product).options(joinedload(Product.category)).filter(
        Product.is_active == True  # noqa: E712
    ).order_by(Product.created_at).all()
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FEED_COLUMNS)
    writer.writeheader()
    writer.writerows(feed_rows(products))
    return buffer.getvalue()


# --- Insights ----------------------------------------------------------------

def _action_value(entries: Optional[list[dict[str, Any]]]) -> float:
    by_type = {entry.get("action_type"): entry.get("value") for entry in entries or []}
    for action in PURCHASE_ACTIONS:
        if action in by_type:
            return float(by_type[action] or 0)
    return 0.0


def summarize(row: dict[str, Any]) -> dict[str, Any]:
    """Flatten an insights row into the numbers the admin report shows."""
    spend = float(row.get("spend") or 0)
    purchase_value = _action_value(row.get("action_values"))
    summary = {
        "spend": spend,
        "impressions": int(row.get("impressions") or 0),
        "reach": int(row.get("reach") or 0),
        "clicks": int(row.get("clicks") or 0),
        "ctr": float(row.get("ctr") or 0),
        "cpc": float(row.get("cpc") or 0),
        "cpm": float(row.get("cpm") or 0),
        "purchases": int(_action_value(row.get("actions"))),
        "purchase_value": purchase_value,
        "roas": round(purchase_value / spend, 2) if spend else 0.0,
    }
    for key in ("date_start", "campaign_id", "campaign_name"):
        if key in row:
            summary[key] = row[key]
    return summary


def ads_report(date_preset: str, client: Optional[MetaClient] = None) -> dict[str, Any]:
    client = client or MetaClient()
    totals = client.insights(date_preset)
    return {
        "date_preset": date_preset,
        "currency": settings.META_CATALOG_CURRENCY,
        "totals": summarize(totals[0]) if totals else summarize({}),
        "daily": [summarize(row) for row in client.insights(date_preset, daily=True)],
        "campaigns": sorted(
            (summarize(row) for row in client.insights(date_preset, level="campaign")),
            key=lambda c: c["spend"], reverse=True,
        ),
    }
