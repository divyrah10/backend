"""Apply launch catalog names, taxonomy, pricing, and copy

Revision ID: 008_catalog_product_details
Revises: 007_order_tracking
Create Date: 2026-09-27
"""

from datetime import datetime
import json
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "008_catalog_product_details"
down_revision: Union[str, None] = "007_order_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PRODUCTS = [
    {
        "old_slug": "brooklyn-city-polo", "slug": "nyc-polo-black", "name": "NYC Polo — Black",
        "category": "men-polos", "price": "2199.00", "sizes": ["S", "M", "L", "XL"],
        "color": "Black", "fit": "Regular", "material": "Cotton piqué", "product_type": "Polo",
        "tagline": "NYC, built from its own skyline.",
        "description": "Black piqué polo with a small left-chest print. The letters are made of towers, with a cab in the C and Brooklyn across the middle. Ribbed collar and cuffs.",
    },
    {
        "old_slug": "texas-wild-west-tee", "slug": "texas-tee-navy", "name": "Texas Tee — Navy",
        "category": "men-t-shirts", "price": "1999.00", "sizes": ["S", "M", "L", "XL"],
        "color": "Navy", "fit": "Dropped shoulder", "material": "100% cotton", "product_type": "T-shirt",
        "tagline": "The front says Texas. The back tells the story.",
        "description": "Navy tee with TEXAS across the chest in ice blue and orange. On the back, the state map is drawn from the Wild West: riders, boots, ropes, a bull. Dropped shoulder.",
    },
    {
        "old_slug": "london-icon-tee", "slug": "london-tee-black", "name": "London Tee — Black",
        "category": "men-t-shirts", "price": "1999.00", "sizes": ["S", "M", "L", "XL"],
        "color": "Black", "fit": "Relaxed", "material": "100% cotton", "product_type": "T-shirt",
        "tagline": "The Eye on the front. Hyde Park on the back.",
        "description": "Black tee. The front is LON in red over DON in white line art, with the London Eye as the O. The back is a pen sketch of Big Ben, the Shard and St Paul's, with a couple walking through Hyde Park.",
    },
    {
        "old_slug": "barcelona-heritage-tee", "slug": "barcelona-tee-white", "name": "Barcelona Tee — White",
        "category": "men-t-shirts", "price": "1699.00", "sizes": ["S", "M", "L", "XL"],
        "color": "White", "fit": "Relaxed", "material": "100% cotton", "product_type": "T-shirt",
        "tagline": "Sagrada Família, with a bull in front of it.",
        "description": "White tee. The left chest has a small football with a red and yellow trail over BARCELONA. The back has a line-drawn bull over a yellow sketch of the Sagrada Família, with BARCELONA in red above.",
    },
    {
        "old_slug": "paris-map-polo", "slug": "paris-polo-black", "name": "Paris Polo — Black",
        "category": "men-polos", "price": "2499.00", "sizes": ["S", "M", "L", "XL"],
        "color": "Black", "fit": "Regular", "material": "Cotton piqué", "product_type": "Polo",
        "tagline": "Paris, drawn as a map.",
        "description": "Black piqué polo. The left chest has a small white PA. The back is a full white line map of the city, from the Arc de Triomphe to Sacré-Cœur, with PARIS in spaced caps below. Ribbed collar and cuffs.",
    },
    {
        "old_slug": "milano-cathedral-tee", "slug": "milano-tee-red", "name": "Milano Tee — Red",
        "category": "men-t-shirts", "price": "2199.00", "sizes": ["S", "M", "L", "XL"],
        "color": "Red", "fit": "Relaxed", "material": "100% cotton", "product_type": "T-shirt",
        "tagline": "The Duomo in cream and orange, on red.",
        "description": "Red tee with a small Duomo over MILANO on the chest. The back carries the full Duomo in cream and orange, with MILANO in thin lettering above.",
    },
    {
        "old_slug": "roma-heritage-crop-tee", "slug": "roma-crop-tee-black", "name": "Roma Crop Tee — Black",
        "category": "women-crop-tees", "price": "1999.00", "sizes": ["XS", "S", "M", "L", "XL"],
        "color": "Black", "fit": "Cropped", "material": "100% cotton", "product_type": "Crop tee",
        "tagline": "Laurels on the front. The whole city on the back.",
        "description": "Black cropped tee. The front has ROMA framed by two laurel branches and a green and a pink brush stroke. The back has ROMA in outlined block letters over the Colosseum, a stone bridge and the river.",
    },
    {
        "old_slug": "milano-heart-crop-tee", "slug": "milano-crop-tee-cobalt-blue", "name": "Milano Crop Tee — Cobalt Blue",
        "category": "women-crop-tees", "price": "1799.00", "sizes": ["XS", "S", "M", "L", "XL"],
        "color": "Cobalt blue", "fit": "Cropped", "material": "100% cotton", "product_type": "Crop tee",
        "tagline": "A pizza-heart on the front. The Duomo on the back.",
        "description": "Cobalt cropped tee. The front has a heart drawn like a pizza, with small hearts as toppings, over MILANO in peach. The back is the Duomo in fine white line work, with MILANO across the base.",
    },
    {
        "old_slug": "berlin-studio-crop-tee", "slug": "berlin-crop-tee-white", "name": "Berlin Crop Tee — White",
        "category": "women-crop-tees", "price": "1699.00", "sizes": ["XS", "S", "M", "L", "XL"],
        "color": "White", "fit": "Cropped", "material": "100% cotton", "product_type": "Crop tee",
        "tagline": "BERLIN, filled with Berlin.",
        "description": "White cropped tee. The left chest has a small red B with yellow bars over BERLIN. The back has BERLIN in block letters filled with sketched landmarks, including the Brandenburg Gate and the TV Tower.",
    },
    {
        "old_slug": "new-york-skyline-crop-tee", "slug": "new-york-crop-tee-navy", "name": "New York Crop Tee — Navy",
        "category": "women-crop-tees", "price": "1999.00", "sizes": ["XS", "S", "M", "L", "XL"],
        "color": "Navy", "fit": "Dropped shoulder crop", "material": "100% cotton", "product_type": "Crop tee",
        "tagline": "New York, mid-splash.",
        "description": "Navy cropped tee with a dropped shoulder. NEW YORK in white across a burst of paint in every colour.",
    },
]


SUBCATEGORIES = [
    ("men-polos", "Polos", "men", 10),
    ("men-t-shirts", "T-shirts", "men", 20),
    ("women-crop-tees", "Crop tees", "women", 10),
]


def upgrade() -> None:
    connection = op.get_bind()
    now = datetime.utcnow()

    for slug, name, parent_slug, sort_order in SUBCATEGORIES:
        existing = connection.execute(sa.text("SELECT id FROM categories WHERE slug = :slug"), {"slug": slug}).first()
        if existing:
            continue
        parent = connection.execute(sa.text("SELECT id FROM categories WHERE slug = :slug"), {"slug": parent_slug}).first()
        if not parent:
            continue
        connection.execute(
            sa.text(
                """
                INSERT INTO categories
                    (id, name, slug, description, parent_id, sort_order, is_active, created_at, updated_at)
                VALUES
                    (:id, :name, :slug, :description, :parent_id, :sort_order, true, :now, :now)
                """
            ),
            {
                "id": uuid.uuid4(), "name": name, "slug": slug,
                "description": f"{name} from the NOT JUST DARK city collection.",
                "parent_id": parent.id, "sort_order": sort_order, "now": now,
            },
        )

    for item in PRODUCTS:
        attributes = json.dumps({
            "sizes": item["sizes"], "color": item["color"], "fit": item["fit"],
            "material": item["material"], "product_type": item["product_type"],
        })
        connection.execute(
            sa.text(
                """
                UPDATE products
                SET name = :name,
                    slug = :new_slug,
                    short_description = :tagline,
                    description = :description,
                    price = :price,
                    compare_at_price = NULL,
                    category_id = (SELECT id FROM categories WHERE slug = :category_slug),
                    attributes = CAST(:attributes AS JSONB),
                    meta_title = :meta_title,
                    meta_description = :meta_description,
                    updated_at = :now
                WHERE slug = :old_slug OR slug = :new_slug
                """
            ),
            {
                "name": item["name"], "new_slug": item["slug"], "old_slug": item["old_slug"],
                "tagline": item["tagline"], "description": item["description"], "price": item["price"],
                "category_slug": item["category"], "attributes": attributes,
                "meta_title": f"{item['name']} | NOT JUST DARK",
                "meta_description": item["tagline"], "now": now,
            },
        )


def downgrade() -> None:
    connection = op.get_bind()
    parent_prices = {
        "brooklyn-city-polo": ("Brooklyn City Polo", "3990.00", "men"),
        "texas-wild-west-tee": ("Texas Wild West Tee", "3290.00", "men"),
        "london-icon-tee": ("London Icon Tee", "3290.00", "men"),
        "barcelona-heritage-tee": ("Barcelona Heritage Tee", "2990.00", "men"),
        "paris-map-polo": ("Paris Map Polo", "4290.00", "men"),
        "milano-cathedral-tee": ("Milano Cathedral Tee", "3290.00", "men"),
        "roma-heritage-crop-tee": ("Roma Heritage Crop Tee", "2990.00", "women"),
        "milano-heart-crop-tee": ("Milano Heart Crop Tee", "2790.00", "women"),
        "berlin-studio-crop-tee": ("Berlin Studio Crop Tee", "2790.00", "women"),
        "new-york-skyline-crop-tee": ("New York Skyline Crop Tee", "2990.00", "women"),
    }
    for item in PRODUCTS:
        old_name, old_price, parent_slug = parent_prices[item["old_slug"]]
        connection.execute(
            sa.text(
                """
                UPDATE products SET name = :name, slug = :old_slug, price = :price,
                    category_id = (SELECT id FROM categories WHERE slug = :parent_slug)
                WHERE slug = :new_slug
                """
            ),
            {"name": old_name, "old_slug": item["old_slug"], "new_slug": item["slug"], "price": old_price, "parent_slug": parent_slug},
        )
    connection.execute(sa.text("DELETE FROM categories WHERE slug IN ('men-polos', 'men-t-shirts', 'women-crop-tees')"))
