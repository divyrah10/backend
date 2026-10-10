from decimal import Decimal, ROUND_HALF_UP

# Catalogue prices are GST-inclusive; this is the rate already inside them.
GST_RATE = Decimal("0.05")


def included_gst(amount: Decimal) -> Decimal:
    """GST portion of a GST-inclusive amount, e.g. 5/105 of it at 5%."""
    return (amount * GST_RATE / (1 + GST_RATE)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
