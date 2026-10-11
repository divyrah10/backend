"""Stock bookkeeping, per size when a product tracks it.

A product with an empty size_stock keeps the old behaviour: one total in
stock_quantity. Once an admin sets per-size counts, size_stock is the source of
truth and stock_quantity is kept equal to its sum, so totals, low-stock alerts
and in_stock keep working unchanged.
"""
from typing import Any, Mapping, Optional

from app.models.product import Product


def product_sizes(product: Product) -> list[str]:
    return list((product.attributes or {}).get("sizes") or [])


def tracks_sizes(product: Product) -> bool:
    return bool(product.size_stock)


def item_size(attributes: Optional[Mapping[str, Any]]) -> Optional[str]:
    return (attributes or {}).get("size")


def available(product: Product, size: Optional[str]) -> int:
    """Units that can still be sold for this product (and size, if tracked)."""
    if tracks_sizes(product):
        return int(product.size_stock.get(size, 0)) if size else 0
    return product.stock_quantity


def adjust(product: Product, size: Optional[str], delta: int) -> None:
    """Reserve (negative delta) or restore (positive) stock."""
    if tracks_sizes(product):
        stock = dict(product.size_stock)  # new dict so SQLAlchemy sees the JSONB change
        if size in stock:
            stock[size] = int(stock[size]) + delta
        product.size_stock = stock
        product.stock_quantity = sum(stock.values())
    else:
        product.stock_quantity += delta


def set_size_stock(product: Product, counts: Mapping[str, int]) -> None:
    """Replace per-size counts; every listed size of the product must be given."""
    sizes = product_sizes(product)
    if not sizes:
        raise ValueError("This product has no sizes")
    unknown = set(counts) - set(sizes)
    if unknown:
        raise ValueError(f"Unknown sizes: {', '.join(sorted(unknown))}")
    missing = [size for size in sizes if size not in counts]
    if missing:
        raise ValueError(f"Missing sizes: {', '.join(missing)}")
    if any(int(value) < 0 for value in counts.values()):
        raise ValueError("Stock cannot be negative")
    product.size_stock = {size: int(counts[size]) for size in sizes}
    product.stock_quantity = sum(product.size_stock.values())
