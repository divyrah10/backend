from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock
from uuid import uuid4
import json
import unittest

import httpx

from app.core.pricing import included_gst
from app.services import shiprocket
from app.services.shiprocket import (
    ShiprocketClient,
    ShiprocketError,
    build_order_payload,
    map_status,
    normalize_phone,
    parse_timestamp,
)


def make_order(**overrides):
    product = SimpleNamespace(sku="LON-TEE-BLK")
    order = SimpleNamespace(
        order_number="ORD-20261010-ABC123",
        created_at=datetime(2026, 10, 10, 14, 30),
        shipping_address={
            "full_name": "Asha Rao Kulkarni",
            "phone": "+91 82174-09487",
            "address_line1": "Vijayshree Nivas",
            "address_line2": None,
            "city": "Dharwad",
            "state": "Karnataka",
            "postal_code": "580001",
            "country": "India",
        },
        user=SimpleNamespace(full_name="Asha", email="asha@example.com", phone=None),
        items=[
            SimpleNamespace(product=product, product_id=uuid4(), product_name="London Tee",
                            quantity=2, unit_price=Decimal("1999.00"), attributes={"size": "M"}),
        ],
        shipping_cost=Decimal("0"),
        discount=Decimal("0"),
        total=Decimal("3998.00"),
    )
    for key, value in overrides.items():
        setattr(order, key, value)
    return order


class PricingTests(unittest.TestCase):
    def test_included_gst_is_five_over_one_oh_five(self):
        self.assertEqual(included_gst(Decimal("1999.00")), Decimal("95.19"))
        self.assertEqual(included_gst(Decimal("0")), Decimal("0.00"))


class MappingTests(unittest.TestCase):
    def test_status_labels(self):
        cases = {
            "DELIVERED": "delivered",
            "RTO DELIVERED": "rto_delivered",
            "RTO_IN_TRANSIT": "rto_in_transit",
            "Out For Delivery": "out_for_delivery",
            "PICKED UP": "picked_up",
            "IN TRANSIT": "in_transit",
            "Pickup Scheduled": "ready_to_ship",
            "UNDELIVERED": "ndr",
            "CANCELED": "cancelled",
            "something new": None,
            None: None,
        }
        for label, expected in cases.items():
            self.assertEqual(map_status(label), expected, label)

    def test_phone_keeps_last_ten_digits(self):
        self.assertEqual(normalize_phone("+91 82174-09487"), "8217409487")
        self.assertEqual(normalize_phone(None), "")

    def test_timestamps(self):
        self.assertEqual(parse_timestamp("2026-10-11 09:05:00"), datetime(2026, 10, 11, 9, 5))
        self.assertIsNone(parse_timestamp("not a date"))


class AddressPhoneTests(unittest.TestCase):
    def test_phone_is_required_and_normalised(self):
        from pydantic import ValidationError
        from app.schemas.address import AddressCreate

        base = dict(full_name="A", address_line1="1 St", city="Dharwad", state="Karnataka", postal_code="580001")
        self.assertEqual(AddressCreate(**base, phone="+91 98765-43210").phone, "9876543210")
        self.assertEqual(AddressCreate(**base, phone="09876543210").phone, "9876543210")
        for bad in (None, "", "12345", "98765432101"):
            with self.assertRaises(ValidationError, msg=bad):
                AddressCreate(**base, phone=bad)


class PayloadTests(unittest.TestCase):
    def test_payload_shape(self):
        payload = build_order_payload(make_order())
        self.assertEqual(payload["order_id"], "ORD-20261010-ABC123")
        self.assertEqual(payload["order_date"], "2026-10-10 14:30")
        self.assertEqual(payload["billing_customer_name"], "Asha")
        self.assertEqual(payload["billing_last_name"], "Rao Kulkarni")
        self.assertEqual(payload["billing_phone"], "8217409487")
        self.assertEqual(payload["billing_address_2"], "")
        self.assertEqual(payload["payment_method"], "Prepaid")
        self.assertEqual(payload["sub_total"], 3998.0)
        self.assertEqual(payload["weight"], 0.6)
        item = payload["order_items"][0]
        self.assertEqual(item["name"], "London Tee (M)")
        self.assertEqual(item["sku"], "LON-TEE-BLK-M")
        self.assertEqual(item["units"], 2)
        self.assertEqual(item["tax"], 5.0)

    def test_uses_razorpay_contact_when_order_has_no_phone(self):
        order = make_order()
        order.shipping_address["phone"] = None
        self.assertEqual(build_order_payload(order)["billing_phone"], "")
        self.assertEqual(build_order_payload(order, fallback_phone="+91 9741 529588")["billing_phone"], "9741529588")

    def test_address_phone_wins_over_fallback(self):
        payload = build_order_payload(make_order(), fallback_phone="+91 9999999999")
        self.assertEqual(payload["billing_phone"], "8217409487")

    def test_falls_back_to_product_id_when_no_sku(self):
        order = make_order()
        order.items[0].product = SimpleNamespace(sku=None)
        order.items[0].attributes = {}
        payload = build_order_payload(order)
        self.assertEqual(payload["order_items"][0]["sku"], str(order.items[0].product_id))


class ClientTests(unittest.TestCase):
    def setUp(self):
        ShiprocketClient._token = None
        self.calls = []

    def client(self, handler):
        def record(request):
            self.calls.append(request)
            return handler(request)
        return ShiprocketClient(httpx.Client(base_url="https://sr.test", transport=httpx.MockTransport(record)))

    def test_logs_in_once_and_reuses_token(self):
        def handler(request):
            if request.url.path == "/auth/login":
                return httpx.Response(200, json={"token": "t1"})
            self.assertEqual(request.headers["Authorization"], "Bearer t1")
            return httpx.Response(200, json={"shipment_id": 42})

        client = self.client(handler)
        client.create_order({})
        client.create_order({})
        self.assertEqual([c.url.path for c in self.calls].count("/auth/login"), 1)

    def test_relogs_in_after_401(self):
        tokens = iter(["old", "new"])

        def handler(request):
            if request.url.path == "/auth/login":
                return httpx.Response(200, json={"token": next(tokens)})
            if request.headers["Authorization"] == "Bearer old":
                return httpx.Response(401, json={"message": "expired"})
            return httpx.Response(200, json={"shipment_id": 7})

        self.assertEqual(self.client(handler).create_order({})["shipment_id"], 7)

    def test_errors_carry_shiprocket_message(self):
        def handler(request):
            if request.url.path == "/auth/login":
                return httpx.Response(200, json={"token": "t"})
            return httpx.Response(422, json={"message": "Invalid pincode"})

        with self.assertRaisesRegex(ShiprocketError, "Invalid pincode"):
            self.client(handler).create_order({})

    def test_validation_errors_name_each_field(self):
        def handler(request):
            if request.url.path == "/auth/login":
                return httpx.Response(200, json={"token": "t"})
            return httpx.Response(422, json={"message": "The given data was invalid.", "errors": {
                "billing_phone": ["The billing phone must be 10 digits."],
                "billing_pincode": ["Invalid pincode"]}})

        with self.assertLogs("app.services.shiprocket", level="WARNING") as logs, \
                self.assertRaisesRegex(ShiprocketError, "billing_phone: The billing phone must be 10 digits") as raised:
            self.client(handler).create_order({})
        self.assertIn("billing_pincode: Invalid pincode", str(raised.exception))
        self.assertIn("billing_phone", logs.output[0])

    def test_awb_not_assigned_raises(self):
        def handler(request):
            if request.url.path == "/auth/login":
                return httpx.Response(200, json={"token": "t"})
            return httpx.Response(200, json={"awb_assign_status": 0, "message": "Insufficient balance"})

        with self.assertRaisesRegex(ShiprocketError, "Insufficient balance"):
            self.client(handler).assign_awb("42")

    def test_bad_login_raises(self):
        with self.assertRaises(ShiprocketError):
            self.client(lambda r: httpx.Response(400, json={"message": "Invalid credentials"})).create_order({})


class StatusSyncTests(unittest.TestCase):
    def test_in_transit_marks_order_shipped(self):
        order = SimpleNamespace(status="processing")
        shipment = SimpleNamespace(status="ready_to_ship", last_synced_at=None)
        shiprocket.apply_status(order, shipment, "in_transit")
        self.assertEqual(order.status, "shipped")
        self.assertEqual(shipment.status, "in_transit")
        self.assertIsNotNone(shipment.last_synced_at)

    def test_record_event_skips_duplicates(self):
        db = mock.Mock()
        shipment = SimpleNamespace(id=uuid4(), events=[])
        when = datetime(2026, 10, 11, 9, 0)
        self.assertTrue(shiprocket.record_event(db, shipment, "in_transit", "In transit", when))
        self.assertFalse(shiprocket.record_event(db, shipment, "in_transit", "In transit", when))
        self.assertEqual(db.add.call_count, 1)


if __name__ == "__main__":
    unittest.main()
