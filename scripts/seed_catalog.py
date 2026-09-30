"""Create or refresh the ten-product launch catalog.

This seed is safe to rerun. It uses public Cloudinary delivery URLs, so a new
developer database does not depend on local image files.
"""

from pathlib import Path
import runpy
import sys
import uuid

from sqlalchemy import or_

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.cache import CacheInvalidator
from app.db.session import SessionLocal
from app.models.category import Category
from app.models.product import Product


CATALOG_MIGRATION = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "008_catalog_product_details.py"
PRODUCTS = runpy.run_path(str(CATALOG_MIGRATION))["PRODUCTS"]
IMAGE_COUNTS = {
    "nyc-polo-black": 3,
    "texas-tee-navy": 3,
    "london-tee-black": 3,
    "barcelona-tee-white": 3,
    "paris-polo-black": 2,
    "milano-tee-red": 2,
    "roma-crop-tee-black": 3,
    "milano-crop-tee-cobalt-blue": 3,
    "berlin-crop-tee-white": 3,
    "new-york-crop-tee-navy": 3,
}
SUBCATEGORIES = [
    ("men-polos", "Polos", "men", 10),
    ("men-t-shirts", "T-shirts", "men", 20),
    ("women-crop-tees", "Crop tees", "women", 10),
]


def image_urls(slug: str) -> list[str]:
    # The launch catalog is public project media. Upload credentials may point
    # to a different Cloudinary environment on a collaborator's machine.
    cloud_name = "fwiewovq"
    base = f"https://res.cloudinary.com/{cloud_name}/image/upload/f_auto,q_auto/not-just-dark/products/{slug}"
    return [f"{base}/{number:02d}" for number in range(1, IMAGE_COUNTS[slug] + 1)]


def get_or_create_category(db, *, slug: str, name: str, parent_id=None, sort_order: int = 0) -> Category:
    category = db.query(Category).filter(Category.slug == slug).first()
    if not category:
        category = Category(
            id=uuid.uuid4(), name=name, slug=slug, parent_id=parent_id,
            sort_order=sort_order, is_active=True,
        )
        db.add(category)
        db.flush()
    return category


def main() -> None:
    with SessionLocal() as db:
        men = get_or_create_category(db, slug="men", name="Men", sort_order=20)
        women = get_or_create_category(db, slug="women", name="Women", sort_order=10)
        parents = {"men": men, "women": women}
        categories = {}
        for slug, name, parent_slug, sort_order in SUBCATEGORIES:
            categories[slug] = get_or_create_category(
                db, slug=slug, name=name, parent_id=parents[parent_slug].id, sort_order=sort_order,
            )

        for item in PRODUCTS:
            product = db.query(Product).filter(
                or_(Product.slug == item["slug"], Product.slug == item["old_slug"])
            ).first()
            if not product:
                product = Product(
                    id=uuid.uuid4(),
                    slug=item["slug"],
                    sku=f"NJD-{item['slug'].upper()}",
                    stock_quantity=30,
                    low_stock_threshold=5,
                    is_featured=True,
                    is_active=True,
                )
                db.add(product)

            product.name = item["name"]
            product.slug = item["slug"]
            product.description = item["description"]
            product.short_description = item["tagline"]
            product.price = item["price"]
            product.compare_at_price = None
            product.category_id = categories[item["category"]].id
            product.images = image_urls(item["slug"])
            product.attributes = {
                "sizes": item["sizes"], "color": item["color"], "fit": item["fit"],
                "material": item["material"], "product_type": item["product_type"],
            }
            product.meta_title = f"{item['name']} | NOT JUST DARK"
            product.meta_description = item["tagline"]
            product.is_active = True

        db.commit()

    CacheInvalidator.invalidate_all_products()
    CacheInvalidator.invalidate_all_categories()
    print(f"Seeded {len(PRODUCTS)} products using Cloudinary-hosted media.")


if __name__ == "__main__":
    main()
