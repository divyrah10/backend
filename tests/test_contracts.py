from uuid import uuid4
import unittest

from pydantic import ValidationError

from app.schemas.order import OrderCreate, OrderItemCreate
from app.schemas.payment import PaymentCreate


class ContractTests(unittest.TestCase):
    def test_payment_create_uses_server_side_order_amount(self):
        payment = PaymentCreate(order_id=uuid4(), currency="INR")
        self.assertEqual(payment.currency, "INR")
        self.assertFalse(hasattr(payment, "amount"))

    def test_order_requires_at_least_one_item(self):
        with self.assertRaises(ValidationError):
            OrderCreate(items=[], shipping_address_id=uuid4())

    def test_order_item_quantity_must_be_positive(self):
        with self.assertRaises(ValidationError):
            OrderItemCreate(product_id=uuid4(), quantity=0)

    def test_order_attributes_are_not_shared(self):
        first = OrderItemCreate(product_id=uuid4(), quantity=1)
        second = OrderItemCreate(product_id=uuid4(), quantity=1)
        first.attributes["size"] = "M"
        self.assertEqual(second.attributes, {})

if __name__ == "__main__":
    unittest.main()
