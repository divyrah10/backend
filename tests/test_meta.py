from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock
from uuid import uuid4
import csv
import io
import json
import unittest

import httpx

from app.services import meta
from app.services.meta import (
    MetaClient,
    MetaError,
    build_purchase_event,
    build_user_data,
    feed_rows,
    normalize_phone,
    sha256,
    summarize,
)


def make_order():
    product = SimpleNamespace(id=uuid4(), sku="LON-TEE-BLK")
    return SimpleNamespace(
        order_number="ORD-20261010-ABC123",
        created_at=datetime.utcnow(),
        user_id=uuid4(),
        user=SimpleNamespace(full_name="Asha", email=" Asha@Example.com ", phone=None),
        shipping_address={
            "full_name": "Asha Rao",
            "phone": "+91 82174-09487",
            "city": "Dharwad",
            "state": "Karnataka",
            "postal_code": "580 001",
            "country": "India",
        },
        items=[SimpleNamespace(product=product, product_id=product.id, quantity=2,
                               unit_price=Decimal("1999.00"), attributes={"size": "M"})],
        total=Decimal("3998.00"),
    )


def make_product(**overrides):
    product = SimpleNamespace(
        id=uuid4(), sku="LON-TEE-BLK", name="London Tee", slug="london-tee",
        description="<p>Heavy   cotton</p>", short_description=None,
        price=Decimal("1999.00"), compare_at_price=Decimal("2499.00"),
        images=["https://img/1", "https://img/2"], attributes={"sizes": ["S", "M"]},
        size_stock={"S": 0, "M": 3}, stock_quantity=3, category=SimpleNamespace(name="Tees"),
    )
    for key, value in overrides.items():
        setattr(product, key, value)
    product.is_on_sale = bool(product.compare_at_price and product.compare_at_price > product.price)
    return product


class UserDataTests(unittest.TestCase):
    def test_phone_gets_country_code(self):
        self.assertEqual(normalize_phone("+91 82174-09487"), "918217409487")
        self.assertEqual(normalize_phone("08217409487"), "918217409487")
        self.assertIsNone(normalize_phone("12345"))

    def test_fields_are_normalised_then_hashed(self):
        data = build_user_data(make_order(), client_ip="1.2.3.4", fbp="fb.1.1.1")
        self.assertEqual(data["em"], [sha256("asha@example.com")])
        self.assertEqual(data["ph"], [sha256("918217409487")])
        self.assertEqual(data["fn"], [sha256("asha")])
        self.assertEqual(data["ln"], [sha256("rao")])
        self.assertEqual(data["zp"], [sha256("580001")])
        self.assertEqual(data["country"], [sha256("in")])
        self.assertEqual(data["client_ip_address"], "1.2.3.4")
        self.assertEqual(data["fbp"], "fb.1.1.1")
        self.assertNotIn("fbc", data)


class PurchaseEventTests(unittest.TestCase):
    def test_event_dedupes_on_order_number_and_uses_catalog_ids(self):
        event = build_purchase_event(make_order(), {})
        self.assertEqual(event["event_name"], "Purchase")
        self.assertEqual(event["event_id"], "ORD-20261010-ABC123")
        self.assertEqual(event["custom_data"]["value"], 3998.0)
        self.assertEqual(event["custom_data"]["content_ids"], ["LON-TEE-BLK-M"])
        self.assertEqual(event["custom_data"]["num_items"], 2)

    def test_old_orders_are_clamped_inside_meta_window(self):
        order = make_order()
        order.created_at = datetime(2020, 1, 1)
        event = build_purchase_event(order, {})
        self.assertGreater(event["event_time"], datetime(2026, 1, 1).timestamp())


class FeedTests(unittest.TestCase):
    def test_one_row_per_size_with_its_own_availability(self):
        rows = feed_rows([make_product()])
        self.assertEqual([r["id"] for r in rows], ["LON-TEE-BLK-S", "LON-TEE-BLK-M"])
        self.assertEqual([r["availability"] for r in rows], ["out of stock", "in stock"])
        self.assertEqual(rows[0]["item_group_id"], "LON-TEE-BLK")
        self.assertEqual(rows[0]["price"], "2499.00 INR")
        self.assertEqual(rows[0]["sale_price"], "1999.00 INR")
        self.assertEqual(rows[0]["description"], "Heavy cotton")
        self.assertTrue(rows[0]["link"].endswith("/products/london-tee"))

    def test_unsized_product_and_missing_images(self):
        rows = feed_rows([
            make_product(attributes={}, size_stock={}, compare_at_price=None),
            make_product(images=[]),
        ])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "LON-TEE-BLK")
        self.assertEqual(rows[0]["sale_price"], "")


class ClientTests(unittest.TestCase):
    def test_send_events_posts_to_pixel_with_test_code(self):
        seen = {}

        def handler(request):
            seen["path"] = request.url.path
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"events_received": 1})

        http = httpx.Client(base_url="https://graph.test/v26.0", transport=httpx.MockTransport(handler))
        with mock.patch.multiple(meta.settings, META_PIXEL_ID="123", META_CAPI_ACCESS_TOKEN="tok"):
            result = MetaClient(http).send_events([{"event_name": "Purchase"}], test_event_code="TEST1")
        self.assertEqual(result["events_received"], 1)
        self.assertEqual(seen["path"], "/v26.0/123/events")
        self.assertEqual(seen["body"]["test_event_code"], "TEST1")

    def test_graph_errors_raise(self):
        http = httpx.Client(base_url="https://graph.test", transport=httpx.MockTransport(
            lambda r: httpx.Response(400, json={"error": {"message": "Invalid token"}})))
        with self.assertRaisesRegex(MetaError, "Invalid token"):
            MetaClient(http).send_events([])


class InsightsTests(unittest.TestCase):
    def test_summary_picks_purchases_and_roas(self):
        row = summarize({
            "spend": "1000", "impressions": "5000", "clicks": "120",
            "actions": [{"action_type": "link_click", "value": "120"},
                        {"action_type": "purchase", "value": "4"}],
            "action_values": [{"action_type": "purchase", "value": "7996"}],
        })
        self.assertEqual(row["purchases"], 4)
        self.assertEqual(row["purchase_value"], 7996.0)
        self.assertEqual(row["roas"], 8.0)
        self.assertEqual(summarize({})["roas"], 0.0)


if __name__ == "__main__":
    unittest.main()
